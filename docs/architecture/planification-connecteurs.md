# Connecteurs de pilotage

Le port `SourceTravail` est commun à tous les outils. Chaque adapter déclare ses capacités et ne
fabrique jamais une donnée absente.

## Matrice

| Connecteur | Équipes | Éléments | Cycles | Releases | Dépendances | Temps | Worklogs | Pagination |
|---|---|---|---|---|---|---|---|---|
| Jira | projet | oui | board sprint | versions | issue links | oui | opt-in `worklogs: true` | `nextPageToken` |
| Azure DevOps | projet/équipe | oui | itérations | non | relations | `CompletedWork` opt-in | opt-in `actuals/worklogs` | WIQL `$top/$skip`, batches de 200 |
| Linear | équipe | oui | cycles | non | relations | non | non | curseur GraphQL |
| CSV | équipe | oui | `cycle_id` | `release_id` | fichier dédié | oui | fichier `temps` | locale |

## Configuration Jira

```json
{
  "projet": "PAY",
  "champ_points": "customfield_10016",
  "champ_cycle": "customfield_10020",
  "board_id": 42,
  "worklogs": true
}
```

Le secret reste un PAT `e-mail:jeton` dans `secret_ref` (`env:`/`vault:`), jamais dans la configuration.

## Configuration Azure DevOps

```json
{
  "organisation": "banque",
  "projet": "Paiements",
  "equipe_id": "Paiements",
  "champ_points": "Microsoft.VSTS.Scheduling.StoryPoints",
  "actuals": true
}
```

Le PAT est résolu par `secret_ref`. Les releases ne sont pas exposées par l'API work item standard : la
capacité `releases` vaut `false`.

## Configuration Linear

```json
{"equipe_id": "team-id"}
```

Jeton dans `secret_ref`. Linear n'a pas de worklogs ni de releases dans le modèle utilisé : les capacités
correspondantes sont déclarées `false`.

## Configuration CSV

- travail : `chemin`, `temps`, `dependances` ;
- people : `chemin`, `allocations`, `absences` ;
- finance : `budgets`, `couts`, `taux` ;
- incidents : `chemin`.

Les dates sont ISO (`YYYY-MM-DD`), les unités `points`, `heures`, `jours`, `items` ou `pourcentage`.
Un élément de travail est dédupliqué par `(equipe_id, external_id)`, la source `prioritaire` gagnant.

## Validation

Les tests contrat vérifient les méthodes communes, les capacités déclarées et les fabriques. Les appels
réseau réels Jira/ADO/Linear restent à valider avec un tenant et des credentials fournis.
