# Contrat de réponse architecture

Séparer explicitement :

- impact prouvé (graphe/preuve) ;
- impact inféré (à vérifier) ;
- impact inconnu (absence de preuve).

Chaque opération observée porte sa posture `observer` ou `agir`. Une écriture est marquée
`approbation requise`. Une relation absente n'est pas une preuve d'absence.
