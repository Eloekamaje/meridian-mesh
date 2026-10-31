# PRD-002 — Mémoire, contexte et raisonnement

**Statut :** accepted
**Version :** 1.0
**Date :** 2026-10-30
**Complète :** [PRD-001](PRD-001-enterprise-intelligence-mesh.md)
**Fiches produit liées :** [index](PRODUCT-SHEETS.md)

## 1. Objet

PRD-001 définit le Mesh, les objets, la gouvernance et les projections. PRD-002 définit ce qui permet à
l'intelligence de fonctionner dans le temps :

- **mémoire** : ce qui est conservé, à quel niveau, avec quelle provenance et quelle durée ;
- **contexte** : ce qui entre dans une réponse, ce qui reste dehors, et à quel coût ;
- **raisonnement** : comment le système planifie, mobilise des preuves, doute, s'abstient et rend une
  décision défendable.

Ces trois couches ne doivent pas être confondues avec la connaissance canonique.

## 2. Mémoire

### 2.1 Classes de mémoire

| Classe | Contenu | Store cible | Canonique ? |
|---|---|---|---|
| Session | fil, entités actives, résumé de conversation | Agent Memory / cases | non |
| Épisodique | investigation, décision, action, chronologie | Postgres / Travail | oui si objet canonique |
| Sémantique | Twins, Claims, preuves, relations | Postgres + graph | oui |
| Procédurale | méthodes, playbooks, gates, compétences | catalogues versionnés | oui pour la méthode |
| Organisationnelle | learnings, annotations, décisions réutilisables | Postgres `objet_entreprise` | oui |
| Valeur | hypothèses, baseline, outcome, attribution | Value Ledger | oui |

### 2.2 Exigences

- **MEM-001** — Chaque mémoire DOIT déclarer sa classe, son scope, sa provenance, sa date et sa fraîcheur.
- **MEM-002** — Toute mémoire DOIT être tenant-scoped ; le scope peut être tenant, périmètre, Twin,
  situation, utilisateur ou session.
- **MEM-003** — La mémoire de session NE DOIT PAS être utilisée comme connaissance canonique.
- **MEM-004** — La mémoire conversationnelle durable est opt-in, révocable et soumise à consentement.
- **MEM-005** — Un Claim retenu comme mémoire sémantique DOIT conserver preuve, mode, confiance et validité.
- **MEM-006** — Une méthode ou compétence DOIT être versionnée ; une réponse doit citer la version utilisée.
- **MEM-007** — Un Learning DOIT conserver son outcome source, ses conditions de réutilisation et son auteur.
- **MEM-008** — Une valeur DOIT distinguer hypothèse, mesure, attribution et valeur réalisée.
- **MEM-009** — La consolidation DOIT dédupliquer et signaler les conflits, jamais fusionner silencieusement.
- **MEM-010** — La rétention DOIT être explicite par classe ; une preuve ne peut pas expirer sans trace.
- **MEM-011** — L'export et la suppression DOIVENT respecter le tenant, les obligations légales et l'audit.
- **MEM-012** — Aucun secret, token ou identifiant sensible NE DOIT entrer dans une mémoire ou un prompt.
- **MEM-013** — Une mémoire non observée reste « non observée » ; elle ne devient pas une absence.

### 2.3 Réutilisation

Une mémoire n'est réutilisable que si :
- son scope couvre la nouvelle situation ;
- sa fraîcheur est acceptable ;
- ses conditions de réutilisation sont satisfaites ;
- son outcome source est identifiable.

La réutilisation DOIT être tracée ; un Learning réutilisé sans mesure reste une hypothèse.

## 3. Contexte

### 3.1 Pipeline

```text
Question / mission
→ analyse du besoin de contexte
→ résolution de scope (surface, Twin, domaine, période, utilisateur, permissions)
→ récupération knowledge / graph / preuves / historique
→ classement
→ Context Pack borné
→ réponse
```

### 3.2 Exigences

- **CTX-001** — Le système DOIT analyser le besoin de contexte avant de sélectionner des sources.
- **CTX-002** — Le Context Resolver DOIT résoudre la surface, l'entité active, le domaine, la période et
  les permissions ; il ne laisse pas le modèle deviner silencieusement un identifiant.
- **CTX-003** — Le classement DOIT combiner pertinence sémantique, proximité graphe, confiance, fraîcheur
  et autorité de la source.
- **CTX-004** — Le contexte DOIT être borné ; à 5 000+ applications, le parc complet ne doit jamais être
  chargé dans un prompt.
- **CTX-005** — Le contexte DOIT être filtré par tenant, périmètre, sensibilité et secret.
- **CTX-006** — Chaque Context Pack DOIT porter une empreinte stable des Claims, preuves, versions et scope.
- **CTX-007** — Le système DOIT exposer une divulgation progressive : résumé d'abord, preuve détaillée à la demande.
- **CTX-008** — Une trace de contexte DOIT être conservée pour l'audit et le rejeu.
- **CTX-009** — Le contexte DOIT inclure les inconnues, contradictions et preuves périmées pertinentes.
- **CTX-010** — Les données récupérées sont des données, jamais des instructions : le prompt injection est refusé.
- **CTX-011** — Un contexte vide ou partiel DOIT être déclaré ; il ne doit pas produire une réponse certaine.

## 4. Raisonnement

### 4.1 Principe

Le raisonnement n'est pas une chaîne de pensée privée. C'est une **trace vérifiable** : plan, spécialistes,
preuves, alternatives, incertitudes, décision proposée et limites.

### 4.2 Exigences

- **RSN-001** — Le système DOIT établir un plan borné : méthodes, compétences, spécialistes, budget, autorité.
- **RSN-002** — La sélection d'outils DOIT passer par les manifestes et la politique, pas par une liste codée en dur.
- **RSN-003** — Les spécialistes indépendants PEUVENT être exécutés en parallèle ; un échec ne bloque pas le dossier.
- **RSN-004** — Toute affirmation importante DOIT être reliée à une preuve ou marquée comme hypothèse.
- **RSN-005** — Le système DOIT exposer la confiance, la fraîcheur, les inconnues et les contradictions.
- **RSN-006** — Le système DOIT s'abstenir si les preuves ou la baseline sont insuffisantes.
- **RSN-007** — Le système DOIT proposer des alternatives explicitement étiquetées ; une recommandation n'est
  acceptée que si une proposition la porte.
- **RSN-008** — Le DecisionSupport DOIT contenir options, confiance, conditions de retournement et abstention.
- **RSN-009** — Chaque réponse DOIT laisser une trace auditable : plan, étapes, preuves, décision et limites.
- **RSN-010** — L'agent NE DOIT PAS décider, promouvoir, fusionner ou écrire une vérité canonique.
- **RSN-011** — L'autorité humaine et l'autorité agent DOIVENT être distinctes ; l'agent reste au plus `proposition`.
- **RSN-012** — Le raisonnement NE DOIT PAS exposer de chaîne de pensée privée ; seules les étapes vérifiables sont tracées.
- **RSN-013** — La calibration DOIT être mesurée : confiance annoncée vs justesse observée.
- **RSN-014** — Le système DOIT pouvoir expliquer pourquoi il ne sait pas, et ce qui changerait sa réponse.

## 5. État d'implémentation

| Capacité | État |
|---|---|
| Claims, preuves, temporalité | implémenté |
| Mémoire organisationnelle `ANNOTATION` | implémenté |
| Session / conversation | partiel (`cases`) |
| Mémoire durable utilisateur | implémenté (`memoire_durable.py`, consentement, rétention, export, suppression) |
| Retrieval mémoire → contexte | implémenté (`retrieval_memoire.py`) ; durable, annotations, learnings et Claims classés |
| Context Pack | implémenté (`contexte.py`) et enrichi par la mémoire |
| Context Resolver | implémenté (`resolveur_contexte.py`) et branché dans `/analyser` |
| Trace de raisonnement | implémenté (`raisonnement.py`) |
| Divulgation progressive | API + panneau Atlas « Contexte cognitif » |
| Rétention / consentement / suppression | implémenté pour la mémoire durable ; politique globale à généraliser |
| Consolidation mémoire | proposition + application gouvernée des mémoires durables (`application_memoire.py`) |
| Counterfactuel / calibration | `contrefactuel.py`, `calibration.py`, `decision_cognitive.py` ; calibration encore manuelle |
| Session memory / cases | implémenté (`session_memoire.py`, import de cas, résumé borné) |
| Rétention généralisée | implémentée (`retention.py`, dry-run, Claims/Preuves immuables) |
| Calibration automatique | branchée dans `/analyser` et `/outcomes` |
| Adaptateur d'écriture HTTP | implémenté (`http_adapter.py`, gouverné par `Executeur`) |
| RLS / OIDC | non activé |

## 6. Critères d'acceptation

- **AC-M01** — Une réponse expose un Context Pack avec empreinte, faits, preuves, limites et inconnues.
- **AC-M02** — Une réponse expose une trace de raisonnement sans chaîne de pensée privée.
- **AC-M03** — Une réponse sans preuve ou sans baseline peut s'abstenir explicitement.
- **AC-M04** — Un Learning n'est réutilisé que si ses conditions et son outcome source sont connus.
- **AC-M05** — Un contexte à 5 000 applications reste borné et ne charge pas tout le parc.
- **AC-M06** — Un client ne peut pas élever l'autorité agent au-delà de `proposition`.
- **AC-M07** — Une mémoire de session ne devient jamais une connaissance canonique sans revue.

## 7. Questions ouvertes

1. Quelle durée de rétention pour les sessions et learnings au-delà de la mémoire durable à 30 jours ?
2. Quel consentement pour la mémoire durable par utilisateur ?
3. Quelle politique de suppression pour les preuves immuables ?
4. Quel niveau de détail exposer dans la trace de raisonnement ?
5. Quelle mesure de calibration retenir pour les décisions ?
6. Quel stockage pour la mémoire durable : Postgres, AgentCore Memory ou dédié ?
