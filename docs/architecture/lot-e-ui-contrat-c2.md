# Lot E UI — contrat C2 pour la trace canonique d'un Travail

Statut : le lot E est **front-only**. Le backend C2 doit fournir la trace canonique
dans la réponse `GET /cases/{id}` ; le front ne fabrique jamais cet identifiant en production.

## Contrat producteur C2

```json
{
  "boucle": {
    "id": "dec-1",
    "statut": "DECIDED",
    "chaine": [
      { "id": "sit-1", "type": "SITUATION", "titre": "Latence des paiements" },
      { "id": "inv-1", "type": "INVESTIGATION", "titre": "Comprendre le goulot" },
      { "id": "dec-1", "type": "DECISION", "titre": "Automatiser", "statut": "DECIDED" }
    ]
  }
}
```

- `chaine` va de la racine jusqu'à l'objet courant.
- Chaque étape expose au minimum `id` et `type` ; `titre` et `statut` sont utilisés
  lorsqu'ils sont présents.
- Si C2 ne peut fournir que l'identifiant, exposer `boucle_id` (et éventuellement
  `boucle_statut`). Le front appelle alors
  `GET /boucle/objets/{id}?historique=true` pour reconstruire la trace.
- Aucun mock de production n'est installé côté lot E : les charges de test vivent
  uniquement dans `TravailDetail.test.jsx`.

## Consommateur lot E

`TravailDetail` accepte `cas.boucle`, `cas.trace_canonique`, `cas.objet_boucle`
ou les champs plats `boucle_id` / `boucle_statut` / `boucle_chaine`.
La trace est affichée en lecture seule au-dessus du fil du Travail, sans modifier
le comportement legacy lorsque la trace est absente.

## Transitions UI

Les transitions canoniques (investigation, décision, initiative, outcome, learning)
passent par `boucleApi` et le contrat A. L'acteur de `trancher` est celui de
l'utilisateur authentifié côté A : l'UI ne l'envoie pas.
