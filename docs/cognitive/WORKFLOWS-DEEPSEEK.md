# Workflows réels avec DeepSeek

Le runtime backend utilise `JUMEAU_MODELE=deepseek` par défaut (`backend/jumeau/agent.py`), avec
`DEEPSEEK_API_KEY` et `deepseek-chat`. Les workflows ci-dessous ont été exécutés sur le backend
local, tenant `demo`, via `POST /api/aurora/demander` — sans Claude Code.

## 1. Incident paiements (global)

- Question : incident de latence paiements depuis 14 h 32, preuves, SLA, limites, propositions.
- Résultat : `200`, **6,50 s**.
- Comportement : `expliquer` ; clarification demandée car l'application « paiements » n'existe pas
  dans le tenant `demo` (seuls Conduit, Gestion des articles et Méridian Mesh sont visibles).
- Aucune action exécutée ; l'absence est formulée comme non prouvée.

## 2. Impact d'un changement sur Conduit

- Question : impact d'un changement sur `conduit`, faits/preuves, distinguer prouvé/inféré, proposer.
- Résultat : `200`, **24,46 s**.
- Usage : 79 343 jetons entrée, 2 876 sortie, 82 219 total ; coût estimé **0,024586 USD**.
- Réponse structurée : dépendances, inconnues, options ; autorité `proposition`.
- Relecture : trois reproches ont été détectés (prise de position implicite, affirmations sans
  citation, confusion fait/inférence), preuve que la relecture fonctionne.

## 3. Runner plugin DeepSeek (2026-11-01)

Le runner [`plugin/meridian/evals/run_deepseek.py`](../../plugin/meridian/evals/run_deepseek.py)
appelle directement `POST /api/aurora/demander` ; **Claude Code n'est pas utilisé**. Backend local
temporaire port `8002`, `JUMEAU_MODELE=deepseek`, tenant `demo`, un run par scénario :

| Scénario | HTTP | Durée | Jetons entrée | Jetons sortie | Coût estimé | Critères |
|---|---:|---:|---:|---:|---:|---|
| `incident-paiements` | 200 | 36,942 s | 188 426 | 3 272 | 0,054474 USD | échec |
| `changement-reglementaire` | 200 | 31,454 s | 150 878 | 3 403 | 0,044480 USD | échec |

Modèle rapporté : `deepseek-chat`. **2/2 runs complets**, **0/2 scénarios** au sens des critères.
Les réponses constatent que Conduit ne contient ni paiement ni règle R-118 et n'inventent pas de
cause. Les critères échouent parce que les Twins du pilote sont absents du tenant et parce que
`/aurora/demander` renvoie de la prose, pas le contrat de sections du plugin. Détail :
[`PILOT-2026-11-01.md`](../../plugin/meridian/evals/PILOT-2026-11-01.md).

## Limites

- L'ancien harness `run_benchmark.py` appelle Claude Code ; il a été tenté mais bloqué par le
  crédit API (0/2, 0 $). Il n'a pas servi aux runs DeepSeek ci-dessus.
- Le tenant `demo` ne contient pas les Twins du pilote (`paiements`, `comptes`, `fraude`, `support`) ;
  le premier workflow demande donc une clarification au lieu d'inventer.
- Aucune revue humaine ni outcome réel ; ce n'est pas une validation de production.
