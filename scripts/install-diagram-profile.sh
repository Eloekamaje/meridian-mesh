#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$HOME/.diagram-design/profiles"
cp "$ROOT/docs/diagrammes/profile-meridian.md" "$HOME/.diagram-design/profiles/meridian.md"
printf 'Profil installé : %s\n' "$HOME/.diagram-design/profiles/meridian.md"
