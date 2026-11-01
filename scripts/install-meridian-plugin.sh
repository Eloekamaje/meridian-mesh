#!/usr/bin/env bash
# Installe le plugin Méridian dans le harness Claude Code local (projet uniquement).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="$REPO_ROOT/plugin/meridian"
MANIFEST="$PLUGIN_ROOT/meridian.plugin.json"
SKILLS_DIR="$REPO_ROOT/.claude/skills"

API_URL="${MERIDIAN_API_URL:-http://127.0.0.1:8001/api}"
TENANT="${MERIDIAN_TENANT:-demo}"
PERSONA="${MERIDIAN_PERSONA:-architecte}"
CHECK_ONLY=0
APPLY_MCP=0

usage() {
  cat <<'EOF'
Usage: scripts/install-meridian-plugin.sh [options]

Vérifie le manifeste, crée les liens .claude/skills/meridian-* et imprime la
commande `claude mcp add`. Aucune configuration globale n'est modifiée.

Options:
  --check             Vérifie seulement (ne crée aucun lien, n'ajoute aucun MCP).
  --apply-mcp         Exécute `claude mcp add --scope project` après vérification.
  --tenant <id>       Tenant MCP (défaut: demo, ou MERIDIAN_TENANT).
  --persona <id>      Persona MCP (défaut: architecte, ou MERIDIAN_PERSONA).
  --api-url <url>     URL de l'API Méridian (défaut: http://127.0.0.1:8001/api).
  -h, --help          Affiche cette aide.

Variables: MERIDIAN_PYTHON force l'interpréteur du MCP. Sinon le script utilise
backend/.venv/bin/python s'il existe, puis python3.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --apply-mcp) APPLY_MCP=1 ;;
    --tenant) TENANT="${2:?valeur manquante pour --tenant}"; shift ;;
    --persona) PERSONA="${2:?valeur manquante pour --persona}"; shift ;;
    --api-url) API_URL="${2:?valeur manquante pour --api-url}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Option inconnue : $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ ! -f "$MANIFEST" ]]; then
  echo "Manifeste introuvable : $MANIFEST" >&2
  exit 1
fi

if [[ -n "${MERIDIAN_PYTHON:-}" ]]; then
  PYTHON_BIN="$MERIDIAN_PYTHON"
elif [[ -x "$REPO_ROOT/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/backend/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "Interpréteur Python introuvable (définir MERIDIAN_PYTHON)." >&2
  exit 1
fi

echo "Manifeste : $MANIFEST"
echo "Python MCP : $PYTHON_BIN"

VERIFY_OUT="$("$PYTHON_BIN" - "$MANIFEST" "$PLUGIN_ROOT" "$REPO_ROOT" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
plugin_root = Path(sys.argv[2])
repo_root = Path(sys.argv[3])
errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    print(f"Manifeste illisible : {exc}", file=sys.stderr)
    sys.exit(1)

require(manifest.get("schema") == "meridian.plugin/1", "schema attendu meridian.plugin/1")
require(manifest.get("name") == "meridian", "name attendu meridian")
require(manifest.get("read_only") is True, "read_only doit valoir true")
require(isinstance(manifest.get("version"), str) and manifest.get("version"), "version manquante")

for key in ("skills", "agents", "domain_packs"):
    values = manifest.get(key)
    require(isinstance(values, list) and values, f"{key} doit être une liste non vide")
    for rel in values or []:
        require((plugin_root / rel).is_file(), f"{key} introuvable : {rel}")

for rel in manifest.get("skills") or []:
    text = (plugin_root / rel).read_text(encoding="utf-8", errors="replace")
    require(text.startswith("---\n"), f"frontmatter YAML absent : {rel}")
    require("name:" in text and "description:" in text, f"name/description absents : {rel}")

for key in ("policy", "response_contract", "profiles"):
    rel = manifest.get(key)
    require(isinstance(rel, str) and (plugin_root / rel).is_file(),
            f"{key} introuvable : {rel}")

mcp = manifest.get("mcp") or {}
require(mcp.get("name") == "meridian", "mcp.name attendu meridian")
require(isinstance(mcp.get("command"), str) and mcp.get("command"), "mcp.command manquant")
require(mcp.get("args") == ["-m", "plugin.meridian.mcp.server"], "mcp.args inattendus")
require(isinstance(mcp.get("env"), dict), "mcp.env doit être un objet")

marketplace = plugin_root / ".claude-plugin" / "marketplace.json"
if marketplace.is_file():
    try:
        data = json.loads(marketplace.read_text(encoding="utf-8"))
        plugins = data.get("plugins") or []
        require(any(p.get("name") == "meridian" for p in plugins),
                "marketplace.json sans plugin meridian")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"marketplace.json invalide : {exc}")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)

print(f"schema\t{manifest['schema']}")
print(f"version\t{manifest['version']}")
for rel in manifest["skills"]:
    print(f"skill\t{rel}")
for rel in manifest["agents"]:
    print(f"agent\t{rel}")
for rel in manifest["domain_packs"]:
    print(f"pack\t{rel}")
PY
)"

printf '%s\n' "$VERIFY_OUT" | while IFS=$'\t' read -r kind value; do
  case "$kind" in
    schema) echo "Schéma valide : $value" ;;
    version) echo "Version : $value" ;;
    skill) echo "Skill : $value" ;;
    agent) echo "Agent : $value" ;;
    pack) echo "Domain pack : $value" ;;
  esac
done

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  if [[ ! -d "$SKILLS_DIR" ]]; then
    echo "Dossier de skills absent : $SKILLS_DIR" >&2
    exit 1
  fi
else
  mkdir -p "$SKILLS_DIR"
fi
missing=0
while IFS=$'\t' read -r kind rel; do
  [[ "$kind" == "skill" ]] || continue
  skill_dir="$(dirname "$PLUGIN_ROOT/$rel")"
  link_name="meridian-$(basename "$skill_dir")"
  link_path="$SKILLS_DIR/$link_name"
  if [[ -L "$link_path" ]]; then
    current="$(readlink -f "$link_path" 2>/dev/null || true)"
    expected="$(readlink -f "$skill_dir")"
    if [[ "$current" != "$expected" ]]; then
      echo "Lien incorrect : $link_path -> $current (attendu $expected)" >&2
      missing=1
    else
      echo "Lien OK : .claude/skills/$link_name"
    fi
  elif [[ -e "$link_path" ]]; then
    echo "Chemin existant mais non symbolique : $link_path" >&2
    missing=1
  elif [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo "Lien manquant : .claude/skills/$link_name" >&2
    missing=1
  else
    target="$(realpath --relative-to="$SKILLS_DIR" "$skill_dir")"
    ln -s "$target" "$link_path"
    echo "Lien créé : .claude/skills/$link_name -> $target"
  fi
done <<< "$VERIFY_OUT"

if [[ "$missing" -ne 0 ]]; then
  echo "Installation incomplète (relancer sans --check pour créer les liens)." >&2
  exit 1
fi

MCP_CMD=(claude mcp add meridian --scope project
  --env "PYTHONPATH=$REPO_ROOT"
  --env "MERIDIAN_API_URL=$API_URL"
  --env "MERIDIAN_TENANT=$TENANT"
  --env "MERIDIAN_PERSONA=$PERSONA"
  -- "$PYTHON_BIN" -m plugin.meridian.mcp.server)

echo
echo "Configuration MCP du projet (scope project, pas de config globale) :"
printf ' %q' "${MCP_CMD[@]}"
printf '\n'
echo "Alternative : copier .mcp.json.example vers .mcp.json et l'adapter."

if [[ "$APPLY_MCP" -eq 1 ]]; then
  if ! command -v claude >/dev/null 2>&1; then
    echo "CLI claude introuvable ; commande non exécutée." >&2
    exit 1
  fi
  "${MCP_CMD[@]}"
  echo "MCP meridian ajouté au projet."
else
  echo "Ajout non exécuté (utiliser --apply-mcp pour l'appliquer)."
fi
