# Runner de benchmark Méridian

`run_benchmark.py` rejoue un ou plusieurs scénarios JSON avec la CLI Claude Code, ou importe des
réponses humaines, puis compare quatre bras :

| Bras | Cwd | MCP Méridian | Contexte ajouté |
|---|---|---|---|
| `skill+mcp` (défaut inclus) | racine du dépôt | oui | skills `meridian-*` visibles |
| `checklist+mcp` | répertoire vide | oui | checklist générique neutre |
| `data-only` | répertoire vide | non | pack JSON gelé préfixé au prompt |
| `human` | aucun appel Claude | non | réponse déjà produite, importée |

Le runner ne juge pas la qualité rédactionnelle : il n'évalue que des critères objectifs déclarés
dans le scénario.

## Prérequis

- CLI `claude` disponible dans le `PATH` pour les bras non humains ;
- lancer le runner avec le Python qui possède `mcp` et `requests` (le `.venv` du backend) ;
- backend Méridian joignable via `MERIDIAN_API_URL` ;
- pour `skill+mcp`, les skills doivent être visibles dans `.claude/skills/meridian-*` à la racine
  du dépôt (lien ou plugin installé).

## Utilisation

Depuis `backend/` :

```bash
PYTHONPATH=..:../backend .venv/bin/python ../plugin/meridian/evals/run_benchmark.py \
  --scenario ../plugin/meridian/evals/scenarios/incident-paiements.json \
  --runs 3 \
  --output /tmp/meridian-benchmark
```

Comparer plusieurs bras (option répétable) :

```bash
PYTHONPATH=..:../backend .venv/bin/python ../plugin/meridian/evals/run_benchmark.py \
  --scenario ../plugin/meridian/evals/scenarios/incident-paiements.json \
  --arm skill+mcp \
  --arm checklist+mcp \
  --arm data-only \
  --output /tmp/meridian-benchmark
```

Importer une réponse humaine (aucune CLI Claude lancée) :

```bash
PYTHONPATH=..:../backend .venv/bin/python ../plugin/meridian/evals/run_benchmark.py \
  --scenario ../plugin/meridian/evals/scenarios/incident-paiements.json \
  --arm human \
  --human-dir /tmp/meridian-human \
  --output /tmp/meridian-benchmark
```

Options principales :

| Option | Défaut | Rôle |
|---|---|---|
| `--scenario` | requis, répétable | Fichier JSON de scénario. |
| `--runs` | `3` | Runs par scénario et par bras non humain. |
| `--arm` | `skill+mcp`, `checklist+mcp`, `data-only` | Bras à exécuter, répétable : `skill+mcp`, `checklist+mcp`, `data-only`, `human`. |
| `--with-skill` / `--no-with-skill` | non | Alias historiques de `--arm skill+mcp` / `--arm checklist+mcp`. |
| `--human-dir` | aucun | Dossier des fichiers `<scenario>-human.json` ; sans lui, le bras `human` est marqué manquant. |
| `--mcp-config` | généré | Configuration MCP existante pour les bras MCP. |
| `--model` | non transmis | Modèle Claude Code. |
| `--max-budget-usd` | `1.25` | Budget maximal par run. |
| `--timeout` | `300` | Timeout par run, en secondes. |
| `--output` | `/tmp/meridian-benchmark-<timestamp>` | Répertoire des résultats. |
| `--api-url`, `--tenant`, `--persona` | env puis valeurs Méridian | Env du MCP généré. |
| `--dry-run` | désactivé | Imprime les commandes ou imports sans exécuter ni écrire. |

Sans `--mcp-config`, un fichier temporaire est créé avec `sys.executable`, le module
`plugin.meridian.mcp.server`, `PYTHONPATH` vers la racine du dépôt et les variables
`MERIDIAN_API_URL`, `MERIDIAN_TENANT`, `MERIDIAN_PERSONA`. Aucun MCP n'est créé pour un run
`data-only` ou `human` seul.

Le bras `checklist+mcp` utilise `checklists/generic.md`, ajouté via
`--append-system-prompt`. Cette checklist est générique (faits, preuves, limites, options,
décision, abstention) et ne contient aucun nom de skill Méridian. Le prompt du scénario n'est pas
modifié.

Le bras `data-only` exige un champ `data_pack` dans le scénario. Le fichier JSON est lu au démarrage
et préfixé au prompt avec la mention « données gelées, aucun outil MCP » ; la commande n'inclut ni
`--mcp-config` ni `--strict-mcp-config`, et seuls `Read` et le budget habituel sont transmis.

## Schéma de scénario

Un fichier peut contenir un objet, une liste d'objets, ou un objet `{"scenarios": [...]}`.

```json
{
  "id": "incident-paiements",
  "prompt": "Un incident de latence touche Paiements depuis 14 h. Analyse l'impact, le SLA et les mitigations.",
  "skill": "meridian-incident-ops",
  "mcp_tools": ["meridian_analyser", "meridian_impact"],
  "data_pack": "packs/incident-paiements.json",
  "expected_terms": ["socle", "SLA"],
  "forbidden_terms": ["chaîne causale"],
  "forbidden_terms_exceptions": {"chaîne causale": ["non", "pas"]},
  "expected_sections": ["Limites"],
  "max_seconds": 150,
  "max_cost": 1.25,
  "must_complete": true
}
```

- `mcp_tools` accepte les noms courts (`meridian_analyser`) ou préfixés
  (`mcp__meridian__meridian_analyser`) ; par défaut, tous les tools Méridian read-only sont autorisés.
- `data_pack` est un chemin JSON, relatif au fichier de scénario ou absolu. Il n'est requis que pour
  le bras `data-only` ; un pack absent ou invalide fait échouer le runner en code `2` avant tout
  appel à Claude.
- `expected_terms` et `expected_sections` (ou son alias `sections`) doivent apparaître dans le
  résultat final, sans distinction de casse.
- `forbidden_terms` ne doivent pas apparaître ; `forbidden_terms_exceptions` déclare les négations
  tolérées autour d'un terme.
- `max_seconds` utilise la durée du résultat Claude, ou la durée murale à défaut.
- `must_complete` est vrai par défaut : le run doit produire un résultat final sans timeout ni erreur.

## Packet de revue humaine

Construire un packet aveugle depuis les résultats :

```bash
python ../plugin/meridian/evals/build_human_packet.py \
  --runs-dir /tmp/meridian-benchmark --output /tmp/meridian-human-packet
```

Le packet ne contient aucune revue inventée : les reviewers remplissent les formulaires.

## Réponses humaines

Pour chaque scénario, le bras `human` cherche `<slug>-human.json` (puis `<id>-human.json`) dans
`--human-dir`. Exemple :

```json
{
  "answer": "Réponse complète de l'analyste...",
  "duration_seconds": 900,
  "cost_usd": 0,
  "criteria": [
    {"name": "expected_term:socle", "passed": true, "detail": "présent"},
    {"name": "expected_section:Limites", "passed": true, "detail": "présente"}
  ]
}
```

- `answer` (ou `result`, `response`, `text`) est le texte évalué.
- `criteria` ou `grades` peuvent fournir une notation déjà faite ; sinon le runner applique les
  critères objectifs du scénario au texte.
- `passed` peut forcer le verdict global.
- Un fichier absent, illisible ou un `--human-dir` omis produit un run marqué `missing: true`,
  compté comme échec mais conservé dans le résumé.

## Sorties

```text
<output>/
  summary.json                    # résumé global, comparaison et tous les runs
  <scenario>/
    summary.json                  # résumé du scénario, par bras et comparaison
    skill+mcp/
      run-01.jsonl                # flux JSONL brut
      run-01.result.txt           # texte final
      run-01.json                 # bilan, coût, outils, critères
    checklist+mcp/...
    data-only/...
    human/
      run-01.human.json           # réponse ou marqueur de manque
      run-01.result.txt
      run-01.json
```

`summary.json` contient `summary.by_arm`, l'alias `summary.by_condition`, et `comparison` avec les
écarts de taux de réussite, de coût moyen et de durée moyenne par rapport à `skill+mcp`. Chaque
critère porte un nom et un booléen `passed`. Un run est réussi si tous ses critères passent.

Le code de sortie vaut `0` après exécution, même si des critères échouent ; il vaut `2` en cas de
scénario, de checklist, de data pack ou de configuration invalide.

## Limites

- Le bras `skill+mcp` change le répertoire courant ; Claude Code peut encore voir des skills
  utilisateur installés dans `~/.claude/skills`. Pour un baseline strict, utiliser un environnement
  utilisateur isolé.
- Le runner ne prouve pas une supériorité statistique : `--runs 3` reste un échantillon.
- Les termes interdits sont de simples sous-chaînes ; utiliser des termes discriminants ou les
  exceptions de négation déclarées.
- `human` importe une seule réponse par scénario, indépendamment de `--runs` ; la qualité du verdict
  dépend de la grille fournie ou des critères objectifs du scénario.
- Les résultats et les flux bruts peuvent contenir les réponses complètes : les traiter selon la
  politique de confidentialité du projet.
