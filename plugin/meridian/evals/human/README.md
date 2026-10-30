# Revue humaine des scénarios Méridian

La revue humaine complète le benchmark automatique : elle juge la qualité de la
décision, l'ancrage dans les preuves et la calibration, sans remplacer les
critères objectifs du runner. Chaque revue est un fichier JSON validé par
`review.schema.json`.

## Portée

- Scénarios et paquets de données du tenant `demo` uniquement.
- Aucune donnée personnelle, aucun secret, aucun jeton ne doit être recopié dans
  `comments` ou `critical_errors`.
- La revue est indépendante : le reviewer ne modifie ni le scénario, ni la clé de
  réponse, ni le paquet de données.

## Champs obligatoires

| Champ | Type | Échelle | Rôle |
|---|---|---|---|
| `reviewer_id` | chaîne | — | Identifiant stable du reviewer (pas une adresse personnelle). |
| `scenario` | chaîne | — | Identifiant du scénario, par exemple `incident-preuve-perimee`. |
| `decision_accuracy` | entier | 0–4 | Justesse de la décision ou de l'abstention. |
| `evidence_grounding` | entier | 0–4 | Ancrage des affirmations dans les preuves disponibles. |
| `calibration` | entier | 0–4 | Confiance affichée cohérente avec la preuve et l'incertitude. |
| `usefulness` | entier | 1–5 | Utilité pratique de la réponse pour un décideur. |
| `trust` | entier | 1–5 | Confiance globale accordée à la réponse. |
| `critical_errors` | tableau | — | Erreurs graves, éventuellement vide. |
| `would_approve` | booléen | — | La réponse serait-elle approuvée en l'état ? |
| `time_seconds` | entier | ≥ 0 | Temps de revue mesuré, en secondes. |
| `comments` | chaîne | ≤ 4000 | Justification courte, factuelle et actionnable. |

### Échelles 0–4

- `decision_accuracy` : 0 = décision contraire aux preuves ; 1 = très
  partielle ; 2 = partielle ; 3 = correcte avec réserves ; 4 = correcte,
  justifiée et bornée.
- `evidence_grounding` : 0 = faits inventés ; 1 = majoritairement non étayé ;
  2 = partiellement étayé ; 3 = étayé ; 4 = chaque affirmation importante est
  reliée à une preuve ou à une limite explicite.
- `calibration` : 0 = confiance trompeuse ; 1 = sur-confiance ou sous-confiance
  forte ; 2 = imparfaite ; 3 = raisonnable ; 4 = confiance et abstention alignées
  sur la fraîcheur et la couverture des preuves.

### Erreurs critiques

`critical_errors` contient des objets `{type, description, severity?}`. Types
acceptés : `invented_fact`, `stale_evidence_ignored`,
`unsupported_recommendation`, `false_execution`, `other`. Une erreur critique
impose `would_approve = false`.

## Procédure

1. Lire le scénario, puis le paquet gelé `data/<scenario>.json`.
2. Lire la clé `answer-keys/<scenario>.json` après avoir noté sa propre lecture.
3. Vérifier les points de décision, les preuves requises et la condition
   d'abstention.
4. Remplir une revue par scénario et par reviewer.
5. Calculer les médianes des scores, le taux de `would_approve` et le nombre de
   revues avec au moins une erreur critique.

## Exemple

```json
{
  "reviewer_id": "reviewer-01",
  "scenario": "incident-preuve-perimee",
  "decision_accuracy": 3,
  "evidence_grounding": 4,
  "calibration": 4,
  "usefulness": 4,
  "trust": 4,
  "critical_errors": [],
  "would_approve": true,
  "time_seconds": 240,
  "comments": "La réponse signale la preuve de 47 jours, refuse de confirmer la cause et demande une observation fraîche."
}
```

Validation avec `jsonschema` :

```bash
python - <<'PY'
import json
from jsonschema import validate
schema = json.load(open("plugin/meridian/evals/human/review.schema.json"))
review = json.load(open("ma-revue.json"))
validate(review, schema)
PY
```
