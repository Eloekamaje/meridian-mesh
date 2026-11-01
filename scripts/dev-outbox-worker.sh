#!/usr/bin/env bash
# Démarre le worker outbox / projection graphe en développement (Postgres + Neo4j déjà lancés).
# Usage : scripts/dev-outbox-worker.sh [--une-passe] [--intervalle 0.5] [...]
# Le Gardien doit être lancé avec JUMEAU_GRAPH_PROJECTION=outbox pour n'enfiler que la projection.
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec .venv/bin/python -m jumeau.execution.outbox_worker "$@"
