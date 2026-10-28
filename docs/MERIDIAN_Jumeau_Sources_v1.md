# MÉRIDIAN — Le jumeau et ses sources
## Chaque source répond à une question différente ; même contrat pour toutes ; on croise, on n'empile pas

**Statut :** Validé par l'utilisateur (2026-10-27), à implémenter
**Documents liés :** Architecture Jumeau v1 §4.5 et §7.2, Harness v2, Mobilisation v1, Security Trust Model §90–91

---

# 1. Ce que dit chaque source

| Source (système) | Nature | Ce qu'elle dit | Autorité pour | Faiblesse |
|---|---|---|---|---|
| Git | `code` | ce que l'application **fait** | comportement programmé, règles appliquées | muet sur pourquoi / pour qui |
| Confluence, README | `documentation` | ce qu'elle **est censée** faire, pour qui, pourquoi | intention, acteurs, parcours | souvent périmée |
| Jira | `trajectoire` | **pourquoi** elle a changé, ce qui est prévu | trajectoire, décisions | morcelée |
| Datadog | `comportement` | comment elle **se comporte** | volumes, comportement normal, appels réels | n'explique pas l'intention |
| ServiceNow | `exploitation` | comment elle **échoue** | criticité vécue, incidents | biaisée vers les problèmes |
| Schéma de base | `donnees` | ce qu'elle **détient** | objets métier, sensibilité | ne dit pas l'usage |
| Équipe (revues) | `humain` | ce qui est **confirmé** | le dernier mot | ne couvre pas tout |

# 2. Routage par question (méthode `comprendre-application`)

| Question | Sources d'abord | Puis |
|---|---|---|
| À quoi elle sert | documentation | code, trajectoire |
| Pour qui, dans quels parcours | documentation | trajectoire, code |
| Les informations qu'elle détient | donnees, code | documentation |
| Les règles qu'elle applique | code | documentation (intention de la règle) |
| Avec qui elle échange | comportement, code | documentation |
| Comment elle vit | trajectoire, exploitation, comportement | code (historique) |
| Ce que l'on ne sait pas | ce qu'aucune source branchée ne couvre | |

**Autorité selon la question** : sur ce qu'elle *fait*, le code l'emporte sur la documentation ; sur ce qu'elle *doit
faire*, la documentation et l'équipe l'emportent ; sur son *comportement réel*, l'observabilité l'emporte sur le code.

# 3. Le contrat d'une source (`jumeau/lecteurs.py`)

Toute source branchée d'un jumeau est un **lecteur** qui offre trois choses, et rien d'autre :

1. `chercher(texte)` → résultats `{ref, titre, extrait}` bornés ;
2. `lire(ref, debut, fin)` → `{ref, titre, version, lignes, locator}` : le contenu en lignes de texte, à une version
   donnée ;
3. `verifier(locator)` → la citation existe-t-elle, à cette version, avec ces lignes ?

**Citation** : `systeme://espace/ref@version#Ldébut-Lfin` (ex. `confluence://TBT/123456@7#L4-L9`). Le code garde sa
forme actuelle (`git://dépôt@sha:chemin#L…` ou `chemin#L…`). Le harness vérifie toute citation avant qu'elle ne
prouve quoi que ce soit (Contradicteur, `proposer_connaissance`).

Ajouter une source = écrire un lecteur, enregistrer sa fabrique ; pas de nouveau pipeline. Le contenu lu est une
**donnée**, jamais une instruction ; un lecteur ne lit que ce que son jeton autorise (lecture seule, périmètre).

# 4. L'agent et les sources

- Le prompt annonce les sources branchées du jumeau, avec leur nature et ce pour quoi elles font autorité.
- Outils génériques `chercher_dans(source, texte)` et `lire_dans(source, ref, debut, fin)` pour toute source autre que
  le code (les outils de code restent).
- `proposer_connaissance` accepte une preuve de n'importe quelle source branchée (citation vérifiée).
- La méthode `comprendre-application` route chaque question vers ses sources (§2).

# 5. Croiser, pas empiler

- **Maturité calculée** (Architecture §7.2) : M1 extraite ; M2 une preuve vérifiée ; **M3** preuves de **deux
  systèmes différents** ; **M4** M3 + validée par l'équipe. Deux preuves du même système ne sont pas indépendantes.
- **Contradiction** : quand deux sources se contredisent (« la documentation dit que seuls les conseillers valident,
  le code laisse aussi valider l'agence »), l'agent la signale (`signaler_contradiction`) avec une preuve de chaque
  côté ; le harness vérifie les deux preuves ; la contradiction est un constat de premier plan de la revue
  (« Ce que l'on ne sait pas encore » / contradictions), à trancher par l'équipe.
- Une connaissance prouvée par une seule source garde une confiance plus basse.

# 6. Déclencheurs du gardien

Commit (existant), puis page modifiée (version Confluence), ticket clos, incident : chaque lecteur expose sa
version courante ; le gardien relit les sources qui ont avancé.

# 7. Premier lecteur réel : Confluence

Confluence Cloud (API REST v2) ou Data Center : jeton déposé dans Vault (connexion réutilisable, comme GitHub),
espace choisi dans la commande, pages converties en lignes de texte, version = numéro de version de la page,
recherche par CQL limitée à l'espace. Jira, Datadog, ServiceNow suivront le même contrat.
