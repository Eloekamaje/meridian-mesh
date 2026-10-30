# Runner de benchmark Méridian

`run_benchmark.py` rejoue un ou plusieurs scénarios JSON avec la CLI Claude Code, en comparant
la condition **avec skill** (racine du dépôt, donc `.claude/skills`) et la condition **sans skill**
(répertoire temporaire vide), avec le même serveur MCP Méridian read-only.

Le runner ne juge pas la qualité rédactionnelle : il n'évalue que des critères objectifs déclarés
dans le scénario.

## Prérequis

- CLI `claude` disponible dans le `PATH` ;
- lancer le runner avec le Python qui possède `mcp` et `requests` (le `.venv` du backend) ;
- backend Méridian joignable via `MERIDIAN_API_URL` ;
- pour la condition avec skill, les skills doivent être visibles dans `.claude/skills/meridian-*`
  à la racine du dépôt (lien ou plugin installé).

## Utilisation

Depuis `backend/` :

```bash
PYTHONPATH=..:../backend .venv/bin/python ../plugin/meridian/evals/run_benchmark.py \
  --scenario ../plugin/meridian/evals/scenarios/incident-paiements.json \
  --runs 3 \
  --output /tmp/meridian-benchmark
```

Options principales :

| Option | Défaut | Rôle |
|---|---|---|
| `--scenario` | requis, répétable | Fichier JSON de scénario. |
| `--runs` | `3` | Runs par scénario et par condition. |
| `--with-skill` / `--no-with-skill` | les deux | Restreint les conditions. |
| `--mcp-config` | généré | Configuration MCP existante. |
| `--model` | non transmis | Modèle Claude Code. |
| `--max-budget-usd` | `0.75` | Budget maximal par run. |
| `--timeout` | `180` | Timeout par run, en secondes. |
| `--output` | `/tmp/meridian-benchmark-<timestamp>` | Répertoire des résultats. |
| `--api-url`, `--tenant`, `--persona` | env puis valeurs Méridian | Env du MCP généré. |
| `--dry-run` | désactivé | Imprime les commandes sans exécuter ni écrire. |

Sans `--mcp-config`, un fichier temporaire est créé avec `sys.executable`, le module
`plugin.meridian.mcp.server`, `PYTHONPATH` vers la racine du dépôt et les variables
`MERIDIAN_API_URL`, `MERIDIAN_TENANT`, `MERIDIAN_PERSONA`.

## Schéma de scénario

Un fichier peut contenir un objet, une liste d'objets, ou un objet `{"scenarios": [...]}`.

```json
{
  "id": "incident-paiements",
  "prompt": "Un incident de latence touche Paiements depuis 14 h. Analyse l'impact, le SLA et les mitigations.",
  "skill": "meridian-incident-ops",
  "mcp_tools": ["meridian_analyser", "meridian_impact"],
  "expected_terms": ["socle", "SLA"],
  "forbidden_terms": ["chaîne causale"],
  "expected_sections": ["Limites"],
  "max_seconds": 150,
  "max_cost": 0.75,
  "must_complete": true
}
```

- `mcp_tools` accepte les noms courts (`meridian_analyser`) ou préfixés
  (`mcp__meridian__meridian_analyser`) ; par défaut, tous les tools Méridian read-only sont autorisés.
- `expected_terms` et `expected_sections` doivent apparaître dans le résultat final, sans distinction
  de casse.
- `forbidden_terms` ne doivent pas apparaître.
- `max_seconds` utilise la durée du résultat Claude, ou la durée murale à défaut.
- `must_complete` est vrai par défaut : le run doit produire un résultat final sans timeout ni erreur.

## Sorties

```text
<output>/
  summary.json                    # résumé global + tous les runs
  <scenario>/
    summary.json                  # résumé du scénario
    with-skill/
      run-01.jsonl                # flux JSONL brut
      run-01.result.txt           # texte final
      run-01.json                 # bilan, coût, outils, critères
    without-skill/...
```

Chaque critère porte un nom et un booléen `passed`. Un run est réussi si tous ses critères passent.
Le code de sortie vaut `0` après exécution, même si des critères échouent ; il vaut `2` en cas de
scénario ou de configuration invalide.

## Limites

- Le baseline « sans skill » change le répertoire courant, mais Claude Code peut encore voir des
  skills utilisateur installés dans `~/.claude/skills`. Pour un baseline strict, utiliser un
  environnement utilisateur isolé.
- Le runner ne prouve pas une supériorité statistique : `--runs 3` reste un échantillon.
- Les termes interdits sont de simples sous-chaînes : une négation comme « aucune action exécutée »
  contient « action exécutée ». Utiliser des termes discriminants ou une revue humaine.
- Aucune note humaine ou subjective n'est automatisée.
- Les résultats et les flux bruts peuvent contenir les réponses complètes : les traiter selon la
  politique de confidentialité du projet.
