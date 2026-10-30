# ADR-0008 — Le Travail est un store de travail, pas un objet d'entreprise

- **Statut :** accepted
- **Date :** 2026-10-30
- **Amende :** ADR-0005 (périmètre du modèle d'entreprise), ADR-0007 (ce qui reste dans le legacy)

## Contexte

Les `cases` portent une conversation, une veille, des passations, des visites, des options et des livrables. Ce sont des
**états de travail** produits par l'interaction humain/Flore, pas des faits d'entreprise comparables à un Twin, un Claim
ou une Situation. Les projeter dans les huit familles d'ADR-0005 obligerait à inventer une sémantique (par exemple
`ANNOTATION` ou `PROCESS`) et rendrait la lecture canonique fausse.

La parité Mongo/canonique est déjà à zéro pour les objets d'entreprise : identités, relations, situations et initiatives.
Le reste de Mongo n'est pas un résidu oublié ; c'est le store de travail.

## Décision

1. Les `cases` restent dans un **bounded context Travail** distinct du modèle d'entreprise.
2. Aucune projection `case → objet_entreprise` n'est créée.
3. Mongo reste le store de travail actuel tant qu'un store Travail dédié (Postgres documentaire ou autre) n'est pas
   spécifié avec son contrat de reprise, sa recherche et sa gouvernance.
4. Le retrait de Mongo est borné aux collections canoniques migrées ; il ne inclut pas les `cases` par effet de bord.
5. Toute future migration Travail devra conserver : conversation, historique, veille, passation, visites, options,
   livrables, pièces et liens vers Twins/Situations, avec un test de parité dédié.

## Conséquences

- On ne force pas une fausse unité de modèle pour obtenir un chiffre de migration.
- `/api/cases` et `EcritureTravail` restent sur leur store actuel.
- La dette restante est explicite : un **store Travail** est un chantier produit, pas une projection canonique.
- Le graphe, les Claims, les objets d'entreprise et la Boucle restent la source canonique de l'intelligence d'entreprise.
