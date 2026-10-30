#!/usr/bin/env bash
# Démarre un Neo4j local pour le développement. Aucun secret n'est versionné :
# le mot de passe est généré et écrit dans /tmp/meridian-neo4j.env.
set -euo pipefail
NAME="${NEO4J_NAME:-meridian-neo4j}"
PASS="$(openssl rand -hex 16)"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --rm \
  -p 127.0.0.1:7687:7687 -p 127.0.0.1:7474:7474 \
  -e NEO4J_AUTH="neo4j/$PASS" neo4j:5 >/dev/null
umask 077
cat > /tmp/meridian-neo4j.env <<ENV
GRAPH_STORE=neo4j
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=$PASS
NEO4J_DATABASE=neo4j
ENV
for _ in $(seq 1 30); do
  if docker exec "$NAME" cypher-shell -u neo4j -p "$PASS" "RETURN 1;" >/dev/null 2>&1; then
    echo "Neo4j local prêt : source /tmp/meridian-neo4j.env"
    exit 0
  fi
  sleep 2
done
echo "Neo4j local non prêt" >&2
docker logs --tail 20 "$NAME" >&2
exit 1
