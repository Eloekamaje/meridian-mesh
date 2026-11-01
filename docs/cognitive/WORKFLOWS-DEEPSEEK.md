# Workflows réels avec DeepSeek

Le runtime backend utilise `JUMEAU_MODELE=deepseek` par défaut (`backend/jumeau/agent.py`), avec
`DEEPSEEK_API_KEY` et `deepseek-chat`. Les deux workflows ci-dessous ont été exécutés sur le backend
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

## Limites

- Le benchmark plugin (`run_benchmark.py`) appelle Claude Code ; il a été tenté mais bloqué par le
  crédit API (0/2, 0 $). Le présent rapport mesure le runtime DeepSeek du backend, pas ce runner.
- Le tenant `demo` ne contient pas les Twins du pilote (`paiements`, `comptes`, `fraude`, `support`) ;
  le premier workflow demande donc une clarification au lieu d'inventer.
- Aucune revue humaine ni outcome réel ; ce n'est pas une validation de production.
