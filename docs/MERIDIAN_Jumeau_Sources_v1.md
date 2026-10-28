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

# 8. Deux ancres : identité et substance (décision du 2026-10-27)

- **Ancre d'identité : l'élément de configuration de la CMDB** (périmètre de la source ServiceNow), pour tous les
  jumeaux, avec ou sans code : identité stable, responsable, criticité, relations déclarées. Elle dit *qui* est
  l'application, pas *ce qu'elle fait* (déclarative, peut être périmée).
- **Ancre de substance : ce que l'application fait pour la banque**, la première disponible dans cet ordre : le code
  de la banque (y compris autour d'un progiciel : intégrations, extensions, paramétrage scripté) ; le paramétrage
  exporté et versionné ; les interfaces observées (comportement) ; le schéma de données limité aux tables utilisées ;
  la documentation.
- **Naissance** : un élément de configuration et au moins une source de substance ; le code n'est plus obligatoire.
  Un jumeau sans code le dit (« substance : interfaces observées ») et ses connaissances restent M2 tant qu'une
  seconde source ne les confirme pas.
- **Ancrage** : chaque connaissance issue d'une source se rattache, quand il existe, à un élément de l'ancre de
  substance (fichier ou symbole du code) ; le gardien lit d'abord l'ancre de substance, puis rattache le reste.

# 8. Brancher la source pilote

**Ce que l'utilisateur fournit** : l'hôte Atlassian (`banque.atlassian.net`), l'espace Confluence ou le projet Jira
(sa clé), l'adresse e-mail du compte de test et un jeton d'API (id.atlassian.com, Sécurité, Jeton d'API) déposé dans
Vault sous `meridian/…` au format `e-mail:jeton` (ou, en poste de développement, dans `MERIDIAN_…`). Le compte ne doit
avoir que la lecture de ce périmètre.

**Commande d'essai** (six étapes, OK ou ÉCHEC avec la cause, jamais le jeton ; sans l'un des trois éléments elle
s'arrête sans appel réseau) :

    python -m jumeau.essai_source --systeme confluence|jira --hote banque.atlassian.net \
        --perimetre TBT --secret vault:meridian/confluence/pilote#jeton [--terme mot]

Étapes : authentification, lecture du périmètre, recherche, lecture à une version, vérification d'une citation (et
refus d'une ligne inexistante), version courante.

**Vérifié par la documentation officielle (octobre 2026)** : tous les endpoints appelés existent et ne sont pas
retirés. `/wiki/rest/api/search` (CQL v1) est toujours documenté, seuls les champs utilisateur sont retirés ;
`/rest/api/3/search/jql` est le remplaçant de `/rest/api/3/search`, en cours de retrait (que nous n'appelons pas).
Corrigé : plafond de 100 projets (et non 250) et recherche limitée aux pages.

**Non vérifié tant que l'essai n'a pas tourné avec un vrai compte** : la forme réelle des réponses (les tests
reposent sur des réponses factices conformes aux schémas OpenAPI), l'authentification Basic e-mail:jeton sur le tenant
(SSO, liste d'adresses autorisées), la pertinence de la recherche CQL `text ~` sur un vrai contenu, la cohérence
éventuelle de `search/jql` juste après une modification, les limites de débit réelles (429).
