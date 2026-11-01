# Installation locale du plugin Méridian

Installation **projet**, sans modification de `~/.claude`.

## Prérequis

- dépôt cloné à la racine attendue ;
- backend Méridian joignable (`http://127.0.0.1:8001/api`) ;
- `backend/.venv` avec `mcp` et `requests`, ou `MERIDIAN_PYTHON` vers un Python équivalent ;
- CLI `claude` pour le MCP et les runs.

## Vérifier et lier les skills

```bash
scripts/install-meridian-plugin.sh --check
scripts/install-meridian-plugin.sh
```

Le script contrôle `plugin/meridian/meridian.plugin.json` (schéma, skills, agents,
domain packs, policy, contrat, MCP), puis crée ou vérifie les liens
`.claude/skills/meridian-*`. Il ne remplace jamais un fichier existant.

## Déclarer le MCP

Le script imprime la commande, sans l'exécuter :

```bash
claude mcp add meridian --scope project \
  --env "PYTHONPATH=$PWD" \
  --env MERIDIAN_API_URL=http://127.0.0.1:8001/api \
  --env MERIDIAN_TENANT=demo \
  --env MERIDIAN_PERSONA=architecte \
  -- "$PWD/backend/.venv/bin/python" -m plugin.meridian.mcp.server
```

Pour l'appliquer :

```bash
scripts/install-meridian-plugin.sh --apply-mcp
```

Alternative versionnable : copier `.mcp.json.example` en `.mcp.json`, puis adapter
le chemin Python et l'URL. `.mcp.json` est une configuration locale de projet ; ne
pas le confondre avec la configuration globale.

## Benchmark

Depuis `backend/` :

```bash
PYTHONPATH=..:../backend .venv/bin/python ../plugin/meridian/evals/run_benchmark.py \
  --scenario ../plugin/meridian/evals/scenarios/incident-paiements.json \
  --scenario ../plugin/meridian/evals/scenarios/changement-reglementaire.json \
  --runs 1 --max-budget-usd 1.00 --tenant demo --arm skill+mcp --dry-run
```

Retirer `--dry-run` pour un run réel. `--arm skill+mcp` borne le coût à un seul
run par scénario ; les bras `checklist+mcp` et `data-only` sont optionnels.

## Limites

- Les skills et le MCP sont en lecture seule ; aucune écriture canonique.
- Le tenant `demo` doit contenir les Twins et situations des scénarios.
- Le budget est une borne par run, pas une garantie de qualité.
- Ne pas présenter ce pilote comme une preuve de production.
