#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
RACINE="$(pwd)"
PORT="${MOTO_PORT:-5000}"
HOTE="${MOTO_HOST:-127.0.0.1}"
PYTHON="${PYTHON:-$RACINE/backend/.venv/bin/python}"

case "${1:-moto}" in
  -h|--help)
    printf '%s\n' \
      "Usage : scripts/dev-aws-local.sh [moto|--localstack]" \
      "  moto (défaut) : lance moto_server sur http://${HOTE}:${PORT}" \
      "  --localstack  : lance LocalStack sur http://127.0.0.1:${PORT} (Docker requis)"
    exit 0
    ;;
  moto)
    if ! "$PYTHON" -c "import moto.server" >/dev/null 2>&1; then
      printf '%s\n' "moto absent : $PYTHON -m pip install 'moto[server]>=5,<6'" >&2
      exit 2
    fi
    printf '%s\n' \
      "moto_server : http://${HOTE}:${PORT}" \
      "export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_DEFAULT_REGION=ca-central-1" \
      "export AWS_ENDPOINT_URL=http://${HOTE}:${PORT}" \
      "smoke : backend/.venv/bin/python scripts/aws-local-smoke.py --endpoint \$AWS_ENDPOINT_URL"
    exec "$PYTHON" -m moto.server -H "$HOTE" -p "$PORT"
    ;;
  --localstack|localstack)
    if ! command -v docker >/dev/null 2>&1; then
      printf '%s\n' "Docker requis pour LocalStack" >&2
      exit 2
    fi
    printf '%s\n' \
      "LocalStack : http://127.0.0.1:${PORT}" \
      "export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_DEFAULT_REGION=ca-central-1" \
      "export AWS_ENDPOINT_URL=http://127.0.0.1:${PORT}" \
      "smoke : backend/.venv/bin/python scripts/aws-local-smoke.py --endpoint \$AWS_ENDPOINT_URL"
    exec docker run --rm -p "${PORT}:4566" \
      -e SERVICES=secretsmanager,sqs,events,scheduler \
      localstack/localstack:stable
    ;;
  *)
    printf '%s\n' "mode inconnu : $1 (moto ou --localstack)" >&2
    exit 2
    ;;
esac
