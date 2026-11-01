#!/usr/bin/env bash
# Rattrapage Travail Mongo -> Postgres en développement (Postgres et Mongo déjà lancés).
# Usage : scripts/dev-travail-worker.sh [--une-passe] [--intervalle 5] [--tenant local] [...]
# Les écritures restent Mongo ; ce worker ne fait que tenir le read model Postgres à jour.
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec .venv/bin/python -m meridian.adapters.inbound.worker.travail_worker "$@"
