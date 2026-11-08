#!/usr/bin/env bash
# Mesure automatique des observations vers les Outcomes canoniques (Mongo + outbox C1).
# Usage : scripts/dev-mesure-auto-worker.sh [--une-passe] [--tenant banque] [--lot 100] [...]
# Nécessite JUMEAU_MESURE_AUTO=1, PONT_KEY, MONGO_URL et DB_NAME. Aucun accès Postgres direct.
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec .venv/bin/python -m meridian.adapters.inbound.worker.mesure_auto_worker "$@"
