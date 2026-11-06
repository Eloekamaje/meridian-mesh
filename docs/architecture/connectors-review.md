# Revue des connecteurs — sources de connaissance

**Date :** 2026-11-03  
**Statut :** revue experte ECC, lecture seule + corrections ciblées  
**Périmètre :** Git/GitHub, Confluence, SharePoint, Jira, ServiceNow/CMDB, Datadog, OTLP, planification, pièces

## Verdict

Méridian n’a pas treize sources de connaissance. Il a :

- **deux producteurs automatiques de connaissance** : Git (Claims) et OTLP (assertions observées) ;
- **quatre lecteurs de documentation/trajectoire** : Confluence, SharePoint, Jira, ServiceNow ;
- **un lecteur comportemental** : Datadog ;
- **des connecteurs de planification** : Jira/ADO/Linear/CSV ;
- **des entrées de catalogue non branchées** : PostgreSQL, Oracle, Splunk, Kafka, Apigee, AWS.

« Branché » ne signifie pas « ingéré ». Un lecteur qui compare seulement une version et publie une
situation ne produit pas de Claim.

## Tableau

| Connecteur | Lu réellement | Devient connaissance | Limite |
|---|---|---|---|
| Git/GitHub | clone au SHA, CBM, routes, variables, images | **Oui** : Claims + preuves `git://…@sha` | API GitHub = annuaire ; CBM plafonné |
| OTLP | spans caller/callee, méthode, statut, durée | assertions `observed` | snapshot unique, non planifié |
| Confluence | espaces, pages, CQL, HTML | chunks + preuves à la demande | 250 espaces/500 pages, pas de suppression |
| SharePoint | drive récursif, PDF/DOCX/XLSX/HTML | chunks + preuves à la demande | auth app-only, ACL natives absentes |
| Jira | projets, JQL, tickets, commentaires | preuves à la demande | pas d’extraction automatique, état courant |
| ServiceNow/CMDB | CI, incidents, problèmes, changements | preuves à la demande | CMDB déclarative, pas de relations |
| Datadog | services, agrégats spans, dépendances, monitors | preuves à la demande | une journée, pas de logs détaillés |
| ADO/Linear/CSV | planification | objets de planification | pas connaissance canonique |
| Outils OpenAPI/MCP | manifestes | catalogue d’outils | pas de Claim |

## Corrections appliquées pendant la revue

- une configuration de source refuse désormais un **secret brut** : seules les références
  `vault:`, `env:`, `aws:`, `secretsmanager:` sont persistables ;
- `MAX_LIGNES` de lecture passe à 1000 pour ne pas tronquer silencieusement un document ;
- SharePoint est ajouté aux types de lecteurs planifiables ;
- ACL live et ACL des communautés filtrées avant prompt ;
- import `recherche_refutation` corrigé ;
- tenant de requête utilisé pour le retrieval.

## Défauts encore ouverts

### Critiques

- **Confluence/Jira/ServiceNow/Datadog ne produisent pas de delta** : `veiller_source` compare une
  version globale, pas chaque document.
- **Aucun tombstone documentaire** : un document supprimé à la source reste indexé.
- **Fencing incomplet** : les écritures de curseur ne contrôlent pas toujours le propriétaire du bail.
- **Échec silencieux** : une panne de source peut devenir `SUCCEEDED` avec un curseur inchangé.
- **SharePoint** : ACL natives non synchronisées, client credentials global, pas de test dédié.

### Élevés

- pagination partielle (Confluence, Jira, ServiceNow, Datadog, SharePoint nextLink) ;
- cache en mémoire non scopé tenant/hôte ;
- rate limiting local au processus ;
- pas de `Retry-After` généralisé ;
- pièces S3/GridFS sans préfixe tenant ni chiffrement imposé ;
- pas de test bout en bout « document → Claim → preuve ».

## Décisions recommandées

1. **Séparer lecteur et source ingérée.**
   - lecteur = preuve à la demande ;
   - source ingérée = énumération, delta, tombstone, version par document.

2. **Un plan de contrôle unique.**
   - `source_schedule` pour Git, Confluence, SharePoint, Jira, ServiceNow, Datadog, OTLP ;
   - curseur par source et par document ;
   - état de fraîcheur visible.

3. **Un modèle de preuve commun.**
   - Claim Git, assertion OTLP, chunk documentaire partagent source, version, locator, fraîcheur ;
   - un chunk ne devient Claim que par promotion explicite.

4. **ACL avant lecture.**
   - jamais de document hors périmètre ;
   - ACL natives ou ACL de source fail-closed.

## Priorités produit

- **Git** : différenciant, source du comportement réel.
- **Confluence + Jira** : intention et trajectoire, à condition de citer et de contredire.
- **Datadog + ServiceNow** : comportement et exploitation, pas des catalogues de plus.
- **SharePoint** : suspendu tant que les ACL natives ne sont pas traitées.
- **CMDB/OTLP** : ancrage et tuyau d’observation, pas connaissance canonique.
- **ADO/Linear/CSV** : commodité de planification.

## Preuves de test

```bash
pytest meridian/tests/test_confluence.py \
       meridian/tests/test_jira.py \
       meridian/tests/test_datadog.py \
       meridian/tests/test_github.py \
       meridian/tests/test_servicenow.py \
       meridian/tests/test_connecteurs.py \
       meridian/tests/test_connecteurs_runtime.py \
       meridian/tests/test_connecteurs_runtime_pull.py \
       meridian/tests/test_otlp_source.py \
       meridian/tests/test_lecteurs.py -q
```

Résultat de la revue : **151 passed, 2 skipped**.

## Limite de la revue

Aucun test live contre Confluence, SharePoint, Jira, ServiceNow, Datadog ou AWS n’a été exécuté :
credentials et tenants réels absents. Les conclusions portent sur le code, les tests et les mocks.
