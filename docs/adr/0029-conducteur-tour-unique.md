# ADR-0029 — Un conducteur de tour unique pour le dialogue

**Date :** 2026-11-03
**Statut :** accepted (cible), migration par lots
**Décideurs :** Architecture, Dialogue, Raisonnement, Preuve

## Contexte

Le dialogue de Méridian est réparti entre `dialogue`, `cadrage_conversationnel`,
`noyau_raisonnement`, `epistemie`, `orchestrateur` et les adapters HTTP. Ces couches
classifient la même question différemment, interprètent `sans_questions` chacune à leur
façon et ne partagent pas la même question en attente.

Symptôme observé : une question méta (« pourquoi tu ne l'as pas dessiné ? ») peut rouvrir
un cadrage de périmètre ou une confirmation de présupposé, au lieu d'expliquer la réponse
précédente.

## Décision

Un seul composant possède le tour : `ConducteurTour` (cible). Il séquence et persiste ;
il ne pense pas. Le modèle propose une décision structurée ; le code valide les invariants.

```text
ContexteTour → décision → outils → observations → gates → réponse
```

Invariants :

- un seul `EtatTour` versionné par Travail ;
- au plus une question en attente, persistée et relue ;
- `meta` ne consomme jamais un slot ;
- `sans_questions` est global : aucun blocage de clarification ne le contourne ;
- un résultat d'outil est une observation, jamais la réponse finale ;
- ACL, preuves, Claims et gates restent déterministes et côté serveur ;
- un seul écrivain d'état, avec concurrence optimiste.

## Ce qui est copié d'opencode

- la boucle bornée décision → outil → observation → décision ;
- les appels d'outils typés et les résultats structurés ;
- la trace expurgée des décisions et des outils.

## Ce qui n'est pas copié

- les poids et la chaîne de pensée privée ;
- la mémoire implicite entre sessions ;
- les outils shell/write/edit libres dans le dialogue ;
- l'arrêt laissé au modèle ;
- la compaction comme source de vérité ;
- les permissions côté client ;
- le prompt comme politique de sécurité.

## Migration

1. **Lot 0** : tests de conversation verts, ADR, baseline.
2. **Lot 1a** : acte unique, question ouverte persistée, `epistemie` non bloquante en mode
   clarification externe, `sans_questions` global. Implémenté.
3. **Lot 1b** : `EtatTour` versionné, dual-write, fallback anciens Travaux, CAS. Implémenté.
4. **Lot 2** : enveloppe et entrée uniques ; moteur principal orchestrateur avec repli déterministe de sélection. Implémenté.
5. **Lot 3** : contrat `DecisionTour` et garde serveur branchés avant chaque appel d’outil du Harness ; Strands reste le moteur de dialogue mais ne peut plus appeler un outil sans validation.
6. **Lot 4** : enveloppe unique et gates extraits dans `application/gates_tour.py` ; `noyau_raisonnement` délègue. Implémenté.
7. **Lot 5** : migration batch, shadow, rollback, nettoyage. Script additif livré et appliqué aux 5 Travaux existants ; conversation inchangée.

## Conséquences

- Moins de questions incohérentes et moins de reprises ratées.
- Plus de responsabilités explicites entre dialogue, raisonnement, preuve et ACL.
- Migration progressive, avec anciens champs conservés jusqu'au rollback.
- Risque : un conducteur trop central ; il doit rester un séquenceur, pas un god object.
