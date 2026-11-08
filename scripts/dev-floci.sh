#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
RACINE="$(pwd)"
COMPOSE=(docker compose -f docker-compose.floci.yml)
TF=(terraform -chdir=infra/floci)
ENDPOINT="${FLOCI_ENDPOINT:-http://127.0.0.1:4566}"

attendre_floci() {
  for _ in $(seq 1 40); do
    if curl -fsS "${ENDPOINT}/_floci/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  printf '%s\n' "Floci ne répond pas sur ${ENDPOINT}" >&2
  return 1
}

exiger_terraform() {
  if ! command -v terraform >/dev/null 2>&1; then
    printf '%s\n' "Terraform requis : https://developer.hashicorp.com/terraform/install" >&2
    exit 2
  fi
}

sortie() {
  "${TF[@]}" output -raw "$1"
}

usage() {
  cat <<'EOF'
Usage : scripts/dev-floci.sh <commande>

  build     Construit l'image Floci depuis le clone local (../floci)
  start     Démarre Floci (docker compose -f docker-compose.floci.yml)
  apply     Crée/met à jour les ressources AWS locales avec Terraform
  up        start + apply
  env       Affiche les exports à évaluer pour pointer Méridian vers Floci
  smoke     Vérifie S3, SQS, EventBridge, Scheduler, Secrets, KMS, Logs, IAM
  status    Santé Floci + outputs Terraform
  logs      Suit les logs Floci
  down      Arrête Floci (conserve le volume et l'état Terraform)
  destroy   Détruit les ressources Terraform (Floci doit tourner)
  clean     destroy + arrête Floci + supprime le volume

Exemple :

  scripts/dev-floci.sh up
  eval "$(scripts/dev-floci.sh env)"
  scripts/dev-floci.sh smoke
EOF
}

case "${1:-}" in
  build)
    SOURCE="${FLOCI_SOURCE_DIR:-$(cd .. && pwd)/floci}"
    if [ ! -f "${SOURCE}/docker/Dockerfile" ]; then
      printf '%s\n' "Clone Floci introuvable : ${SOURCE} (définir FLOCI_SOURCE_DIR)" >&2
      exit 2
    fi
    docker build -t "${FLOCI_IMAGE:-floci:local}" "${SOURCE}"
    printf '%s\n' "Image construite. Pour l'utiliser : export FLOCI_IMAGE=${FLOCI_IMAGE:-floci:local}"
    ;;
  start)
    "${COMPOSE[@]}" up -d
    attendre_floci
    printf '%s\n' "Floci prêt : ${ENDPOINT} (console : http://127.0.0.1:4500, démarrage à la première visite)"
    ;;
  apply)
    exiger_terraform
    attendre_floci
    "${TF[@]}" init -input=false
    "${TF[@]}" apply -auto-approve
    ;;
  up)
    exiger_terraform
    "${COMPOSE[@]}" up -d
    attendre_floci
    "${TF[@]}" init -input=false
    "${TF[@]}" apply -auto-approve
    ;;
  env)
    exiger_terraform
    cat <<EOF
export AWS_ENDPOINT_URL="$(sortie endpoint)"
export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_SESSION_TOKEN="test"
export AWS_REGION="$(sortie region)"
export AWS_DEFAULT_REGION="$(sortie region)"
export JUMEAU_AWS_REGION="$(sortie region)"
export JUMEAU_PIECES_STORAGE="s3"
export JUMEAU_PIECES_S3_BUCKET="$(sortie pieces_bucket)"
export JUMEAU_PIECES_S3_PREFIX="local"
export JUMEAU_PIECES_S3_ENDPOINT="$(sortie endpoint)"
export JUMEAU_PIECES_S3_REGION="$(sortie region)"
export JUMEAU_PIECES_S3_FORCE_PATH_STYLE="1"
export JUMEAU_INDEX_STORE="s3"
export JUMEAU_INDEX_BUCKET="$(sortie index_bucket)"
export JUMEAU_INDEX_ENDPOINT="$(sortie endpoint)"
export JUMEAU_INDEX_REGION="$(sortie region)"
export JUMEAU_INDEX_PREFIX="meridian/index"
export JUMEAU_INDEX_SSE="aws:kms"
export JUMEAU_INDEX_KMS_KEY="$(sortie kms_alias)"
export JUMEAU_SESSIONS_S3="$(sortie sessions_bucket)/flore"
# Outbox : SQS direct (le publisher préfère SQS quand cette URL est définie)
export JUMEAU_SQS_QUEUE_URL="$(sortie outbox_queue_url)"
# Bus alternatif provisionné et testé ; le runtime ne le sélectionne pas tant que
# JUMEAU_SQS_QUEUE_URL est définie.
export JUMEAU_EVENTBRIDGE_BUS="$(sortie event_bus)"
export JUMEAU_SCHEDULER_ROLE_ARN="$(sortie scheduler_role_arn)"
export JUMEAU_SCHEDULER_TARGET_ARN="$(sortie wakeup_queue_arn)"
export JUMEAU_SCHEDULER_GROUP="$(sortie scheduler_group)"
export JUMEAU_WEBHOOK_SECRET="aws:$(sortie secret_name)#webhook_secret"
EOF
    ;;
  smoke)
    attendre_floci
    "${RACINE}/backend/.venv/bin/python" "${RACINE}/scripts/floci-smoke.py" \
      --endpoint "${ENDPOINT}"
    ;;
  status)
    attendre_floci
    curl -fsS "${ENDPOINT}/_floci/health" | head -c 600
    printf '\n'
    printf 'UI: '
    curl -fsS "${ENDPOINT}/_floci/ui/status" 2>/dev/null || true
    printf '\n'
    exiger_terraform
    "${TF[@]}" output
    ;;
  logs)
    "${COMPOSE[@]}" logs -f floci
    ;;
  down)
    "${COMPOSE[@]}" down
    ;;
  destroy)
    exiger_terraform
    attendre_floci
    "${TF[@]}" destroy -auto-approve
    ;;
  clean)
    exiger_terraform
    if curl -fsS "${ENDPOINT}/_floci/health" >/dev/null 2>&1; then
      "${TF[@]}" destroy -auto-approve || true
    else
      printf '%s\n' "Floci est arrêté : le state Terraform local sera supprimé avec le volume."
    fi
    rm -f infra/floci/terraform.tfstate infra/floci/terraform.tfstate.backup
    "${COMPOSE[@]}" down -v
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    printf '%s\n' "Commande inconnue : $1" >&2
    usage >&2
    exit 2
    ;;
esac
