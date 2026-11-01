#!/usr/bin/env bash
# Smoke local du chemin outbox -> projection Neo4j.
# Usage : scripts/dev-graphe-e2e.sh
# Ne touche qu'au tenant __smoke_graphe__ (surchargeable via SMOKE_TENANT) et nettoie le graphe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
if [ ! -f /tmp/meridian-neo4j.env ]; then
  echo "/tmp/meridian-neo4j.env absent : lancez scripts/dev-neo4j-light.sh up" >&2
  exit 1
fi
set -a
. /tmp/meridian-neo4j.env
set +a

: "${JUMEAU_PG_DSN:?JUMEAU_PG_DSN requis (backend/.env)}"
if [ "${GRAPH_STORE:-}" != "neo4j" ]; then
  echo "GRAPH_STORE=neo4j requis dans /tmp/meridian-neo4j.env" >&2
  exit 1
fi

PY=".venv/bin/python"
export SMOKE_TENANT="${SMOKE_TENANT:-__smoke_graphe__}"
export SMOKE_TWIN_A="${SMOKE_TWIN_A:-smoke-app-a}"
export SMOKE_TWIN_B="${SMOKE_TWIN_B:-smoke-app-b}"
export SMOKE_REL="${SMOKE_REL:-smoke-rel-1}"

OID="$("$PY" - <<'PY'
import os

import psycopg
from neo4j import GraphDatabase

from jumeau.execution import depot

tenant = os.environ["SMOKE_TENANT"]
driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
)
try:
    with driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as session:
        session.run("MATCH (n:Twin {tenant_id: $tenant}) DETACH DELETE n", tenant=tenant).consume()
finally:
    driver.close()

twins = [
    {"id": os.environ["SMOKE_TWIN_A"], "tenant_id": tenant, "nom": "Smoke A", "type": "APPLICATION"},
    {"id": os.environ["SMOKE_TWIN_B"], "tenant_id": tenant, "nom": "Smoke B", "type": "APPLICATION"},
]
relations = [{
    "id": os.environ["SMOKE_REL"],
    "tenant_id": tenant,
    "source": os.environ["SMOKE_TWIN_A"],
    "cible": os.environ["SMOKE_TWIN_B"],
    "type": "echange",
    "etat": "supposee",
}]
with psycopg.connect(os.environ["JUMEAU_PG_DSN"]) as conn:
    oid = depot.ajouter_outbox(
        conn, tenant, "smoke-graphe", "graph.synchroniser",
        {"twins": twins, "relations": relations},
    )
print(oid)
PY
)"

echo "outbox_id=$OID ; une passe du worker"
"$PY" -m jumeau.execution.outbox_worker --une-passe

SMOKE_OID="$OID" "$PY" - <<'PY'
import os
import sys

import psycopg
from neo4j import GraphDatabase

tenant = os.environ["SMOKE_TENANT"]
oid = int(os.environ["SMOKE_OID"])
ok = False
driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
)
try:
    with psycopg.connect(os.environ["JUMEAU_PG_DSN"]) as conn:
        ligne = conn.execute(
            "SELECT publie_le FROM execution_outbox WHERE id = %s", (oid,)
        ).fetchone()
    publie = ligne is not None and ligne[0] is not None
    with driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as session:
        record = session.run(
            "MATCH (a:Twin {tenant_id: $tenant, id: $a})"
            "-[r:RELATION {tenant_id: $tenant, id: $rel}]->"
            "(b:Twin {tenant_id: $tenant, id: $b})"
            "RETURN a.id AS a, b.id AS b, r.type AS rel_type",
            tenant=tenant,
            a=os.environ["SMOKE_TWIN_A"],
            b=os.environ["SMOKE_TWIN_B"],
            rel=os.environ["SMOKE_REL"],
        ).single()
    ok = publie and record is not None
    print(
        "verification",
        f"publie={publie}",
        f"relation={dict(record) if record else None}",
    )
finally:
    with driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as session:
        session.run("MATCH (n:Twin {tenant_id: $tenant}) DETACH DELETE n", tenant=tenant).consume()
    driver.close()

if not ok:
    print("smoke graphe en échec", file=sys.stderr)
    sys.exit(1)
print(f"OK : projection outbox visible dans Neo4j pour {tenant}")
PY
