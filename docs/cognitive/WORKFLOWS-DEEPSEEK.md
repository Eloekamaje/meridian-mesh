# Workflows réels avec DeepSeek

Le runtime backend utilise `JUMEAU_MODELE=deepseek` par défaut (`backend/meridian/adapters/outbound/llm/agent.py`), avec
`DEEPSEEK_API_KEY` et `deepseek-chat`. Les workflows ci-dessous ont été exécutés sur le backend
local, tenant `pilot` pour le pilote du 2026-11-01, via deux routes complémentaires :

- `POST /api/boucle/analyser` : contrat structuré (`socle`, `lecture`, `limites`, `actions`,
  `autorite`, `prochaines_etapes`, `decision_support`) ;
- `POST /api/aurora/demander` : prose DeepSeek et usage (latence, jetons, coût).

**Claude Code n'est pas utilisé** pour ces runs.

## 1. Incident paiements (tenant `pilot`)

- Question : incident de latence paiements depuis 14 h 32, preuves, SLA, limites, propositions.
- Contexte : situation `sit-latence-paiements`, Twins `paiements`, `comptes`, `fraude`, `support`.
- Contrat : HTTP `200`, sections complètes, preuves synthétiques `SLA`/`preuve`/`R-118`/`limite`.
- Prose : HTTP `200`, `deepseek-chat`, 28,877 s, 149 624 jetons entrée, 3 879 sortie,
  0,044665 USD estimés.

## 2. Changement réglementaire R-118 (tenant `pilot`)

- Question : impact de la règle R-118 sur le parcours de paiement, impact prouvé/inféré/inconnu,
  interface et approbation.
- Contexte : situation `sit-anomalie-fraude`, Twins `fraude` et `paiements`.
- Contrat : HTTP `200`, sections complètes, preuves synthétiques `impact`/`interface`/`approbation`.
- Prose : HTTP `200`, `deepseek-chat`, 23,770 s, 215 195 jetons entrée, 3 102 sortie,
  0,061515 USD estimés.

## 3. Runner plugin DeepSeek (2026-11-01)

Le runner [`plugin/meridian/evals/run_deepseek.py`](../../plugin/meridian/evals/run_deepseek.py)
appelle les deux routes ci-dessus ; **Claude Code n'est pas utilisé**. Backend local temporaire
port `8002`, `JUMEAU_MODELE=deepseek`, tenant `pilot`, un run par scénario :

| Scénario | Contrat | Durée contrat | Durée prose | Jetons entrée | Jetons sortie | Coût estimé | Critères |
|---|---:|---:|---:|---:|---:|---:|---|
| `incident-paiements` | 200 | 0,065 s | 28,877 s | 149 624 | 3 879 | 0,044665 USD | **PASS** |
| `changement-reglementaire` | 200 | 0,059 s | 23,770 s | 215 195 | 3 102 | 0,061515 USD | **PASS** |

Modèle rapporté : `deepseek-chat`. **2/2 runs complets**, **2/2 scénarios** au sens des
critères, **0,106180 USD** estimés au total. Les critères sont notés sur le contrat structuré
et la prose ; les échos de la question sont retirés avant notation. Détail :
[`PILOT-2026-11-01.md`](../../plugin/meridian/evals/PILOT-2026-11-01.md).

Le fixture `pilot` est créé par
[`plugin/meridian/evals/seed_pilot.py`](../../plugin/meridian/evals/seed_pilot.py) :
4 Twins, 2 Situations canoniques, 6 Claims/Preuves synthétiques. Il est idempotent et ne
touche jamais `demo`.

## Limites

- L'ancien harness `run_benchmark.py` appelle Claude Code ; il n'a pas servi aux runs DeepSeek.
- Le fixture `pilot` est synthétique et les prompts des scénarios conservent la mention
  historique `tenant demo` ; le tenant effectif est porté par `X-Tenant: pilot`.
- La surface `situation` de `/boucle/analyser` n'accepte que `situation_id` ; les Twins sont
  vérifiés séparément via `/boucle/twins` et les Claims du tenant portent le contexte.
- `impact` et `approbation` sont satisfaits par le texte du contrat et la prose, pas par une
  section top-level `impact` (pas de graphe Neo4j pour `pilot`).
- Aucune revue humaine ni outcome réel ; ce n'est pas une validation de production.
