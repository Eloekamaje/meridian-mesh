#!/usr/bin/env bash
# Neo4j local léger et opt-in pour la projection graphe.
# Usage : scripts/dev-neo4j-light.sh [up|down|status|env|logs]
# Le mot de passe est généré au premier lancement puis conservé dans /tmp/meridian-neo4j.env (0600).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/docker-compose.neo4j.yml"
ENV_FILE="${NEO4J_ENV_FILE:-/tmp/meridian-neo4j.env}"
ACTION="${1:-up}"
shift || true

usage() {
  echo "Usage : $0 [up|down|status|env|logs]" >&2
  exit 2
}

attendre_bolt() {
  local essais="${1:-60}"
  for _ in $(seq 1 "$essais"); do
    if docker compose -f "$COMPOSE" exec -T neo4j \
      cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1;" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

charger_env() {
  if [ -f "$ENV_FILE" ]; then
    set -a
    . "$ENV_FILE"
    set +a
  fi
  export NEO4J_PASSWORD="${NEO4J_PASSWORD:-dev-only-placeholder}"
}

case "$ACTION" in
  up)
    PORT="${NEO4J_PORT:-7687}"
    if [ "$PORT" = "7687" ] && docker ps --format '{{.Names}}' | grep -qx 'meridian-neo4j'; then
      echo "Le conteneur meridian-neo4j écoute déjà 7687." >&2
      echo "Utilisez-le avec /tmp/meridian-neo4j.env, ou choisissez NEO4J_PORT=7688." >&2
      exit 1
    fi
    if [ -z "${NEO4J_PASSWORD:-}" ] && [ -f "$ENV_FILE" ]; then
      set -a
      . "$ENV_FILE"
      set +a
    fi
    if [ -z "${NEO4J_PASSWORD:-}" ] && [ -n "${NEO4J_AUTH:-}" ]; then
      NEO4J_PASSWORD="${NEO4J_AUTH#*/}"
    fi
    if [ -z "${NEO4J_PASSWORD:-}" ]; then
      NEO4J_PASSWORD="$(openssl rand -hex 16)"
    fi
    export NEO4J_PASSWORD
    docker compose -f "$COMPOSE" up -d
    umask 077
    cat > "$ENV_FILE" <<ENV
GRAPH_STORE=neo4j
NEO4J_URI=bolt://127.0.0.1:${NEO4J_PORT:-7687}
NEO4J_USER=neo4j
NEO4J_PASSWORD=$NEO4J_PASSWORD
NEO4J_DATABASE=neo4j
ENV
    chmod 600 "$ENV_FILE"
    if attendre_bolt; then
      echo "Neo4j léger prêt : source $ENV_FILE"
    else
      echo "Neo4j léger non prêt ; logs :" >&2
      docker compose -f "$COMPOSE" logs --tail 40 >&2
      exit 1
    fi
    ;;
  down)
    charger_env
    docker compose -f "$COMPOSE" down "$@"
    echo "Neo4j léger arrêté (volume conservé ; --volumes pour le supprimer)."
    ;;
  status)
    charger_env
    docker compose -f "$COMPOSE" ps neo4j
    if [ -f "$ENV_FILE" ] && docker ps --format '{{.Names}}' | grep -qx 'meridian-neo4j-light'; then
      if attendre_bolt 1; then
        echo "Bolt OK : ${NEO4J_URI} (base ${NEO4J_DATABASE:-neo4j})"
      else
        echo "Bolt injoignable" >&2
        exit 1
      fi
    fi
    ;;
  env)
    if [ ! -f "$ENV_FILE" ]; then
      echo "$ENV_FILE absent : lancez d'abord $0 up" >&2
      exit 1
    fi
    echo "source $ENV_FILE"
    ;;
  logs)
    charger_env
    docker compose -f "$COMPOSE" logs --tail 100 -f "$@"
    ;;
  *)
    usage
    ;;
esac
