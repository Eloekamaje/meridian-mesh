# MÉRIDIAN — Programme cognitif

## Identité typée, Twin provisoire et découverte perpétuelle

**Statut :** programme directeur, opposable pour la couche cognitive  
**Version :** 1.0  
**Date :** 2026-10-30  
**Décision fondatrice :** [ADR-0001](../adr/0001-identite-typed-twin-discovery.md)  
**Périmètre :** identité applicative, résolution, Twin, découverte, interfaces, connecteurs, Mesh, orchestration, sécurité, évaluation  
**Hors périmètre immédiat :** types de Twin non applicatifs, promotion automatique, écriture vers les systèmes sources, graphe inter-tenant

> **En une page.**
> 1. Une **Application** est l'entité métier canonique ; un **Twin** la représente ; un **DiscoveryRun** la découvre ; un **SourceArtifact** la prouve.
> 2. Un dépôt n'est jamais une Application, ni un alias d'Application : il entre par le **routeur d'artefacts**.
> 3. Un **Twin provisoire** répond avec une identité marquée et propose sa nomination/promotion.
> 4. Une absence est « **non observé** » ; une source en échec rend la résolution **inconclusive**.
> 5. La promotion est **humaine ou signée** ; jamais un effet de bord d'un dépôt, d'un mock ou d'un modèle.
> 6. Les **interfaces** sont versionnées ; les **connecteurs** sont déterministes ; le **tenant**, les **secrets**, l'**audit** et la **lecture seule** sont des invariants.

> **Langage normatif.** « DOIT » et « NE DOIT PAS » sont des invariants testables. « DEVRAIT » signale une bonne pratique dont l'écart doit être justifié. Un « test » désigne un test automatisé, un test d'architecture, ou un cas du jeu d'or explicitement cité.

---

## 0. Objet, statut et règle de lecture

Ce document n'est pas un catalogue d'idées. C'est le contrat de construction de la couche cognitive de Méridian : ce qui doit être vrai, dans quel ordre, avec quelles preuves, et comment le mesurer.

Il tranche les ambiguïtés qui ont conduit l'implémentation actuelle à confondre :

1. **l'entité métier Application** et sa **représentation Twin** ;
2. le **Twin** et le **processus de découverte** qui l'entretient ;
3. un **artefact source** (dépôt, configuration, document) et une **Application** ;
4. une **assertion** (déclarée, observée, inférée) et une **vérité canonique** ;
5. une **interface** (contrat versionné, opérations, bindings) et une **connaissance en texte libre** ;
6. le **tenant** (frontière de sécurité) et l'**espace** ou la **persona** (contexte d'usage).

### 0.1 Ce que ce programme remplace ou précise

| Document antérieur | Ce qui reste valide | Ce que ce programme précise ou remplace |
|---|---|---|
| `MERIDIAN_Domain_Model_Information_Architecture_v1.md` §4–5 | Twin = représentation vivante ; identité stable ; Claims et preuves | Pour le périmètre cognitif actuel, **Twin = Twin d'application**. Les autres types de Twin sont différés. Le champ `ApplicationTwin.repositories` est remplacé par des liens `TwinArtifactLink` vers des `SourceArtifact`. Un dépôt n'est jamais un attribut d'identité. |
| `MERIDIAN_Architecture_Jumeau_v1.md` §5 | Chaîne Source → Preuve → Claim → Relation ; maturité M1–M5 ; gouvernance humaine | La relation directe `twin → source` devient `Application ← Twin → SourceArtifact` via le registre d'artefacts. Le Twin n'est pas l'Application. |
| `MERIDIAN_Jumeau_Sources_v1.md` §8 | Deux ancres : identité et substance | L'élément de configuration CMDB est une **assertion d'identité externe**, pas l'Application elle-même. Le code et la configuration sont des **artefacts de substance**, pas des Applications. |
| `MERIDIAN_Jumeau_Mobilisation_v1.md` | Deux portes par Twin ; cartes lisibles ; contributions bornées | La carte expose les **artefacts** et le **Twin**, jamais un nom de dépôt comme alias d'Application. Le routage par dépôt passe par le routeur d'artefacts. |
| `MERIDIAN_Discovery_Maturation_Engine_v1.md` | Signal, Situation, maturation, priorisation | Le présent `DiscoveryRun` est la **découverte d'identité et de représentation** (artefacts, Twins, Applications, interfaces). Il ne remplace pas le moteur de Situations, qui consomme le Mesh et les Claims. |
| `MERIDIAN_Plan_Remediation_v1.md` | Honnêteté des preuves, maturité, séparation réel/démo | Ce programme ajoute la couche identité manquante. Il ne rouvre pas les corrections déjà faites. |

Dans ce document, **Twin** désigne le jumeau applicatif. Le module `backend/jumeau` et la table `jumeau` conservent leur nom pendant la migration et désignent l'implémentation historique du Twin ; ils ne désignent ni l'Application ni le processus de découverte.

### 0.2 Portée de la première application

La première application du modèle est **applicative**. Une Application est une application logicielle exploitée par une organisation, avec un propriétaire, un cycle de vie et des interfaces. Les Twin de processus, capacité, parcours, organisation ou produit restent possibles plus tard, mais ils devront reprendre les mêmes séparations : entité canonique, représentation, processus, artefact. Ils ne sont pas dans ce programme.

Le programme couvre la **substrate cognitive d'identité et de représentation**. Flore, les méthodes, la mémoire personnelle, le Travail et le moteur de Situations restent des couches existantes ; elles consomment cette substrate et ne la remplacent pas. Une réponse de Flore n'est fiable que si l'identité qu'elle mobilise l'est.

---

## 1. Problème et invariants

### 1.1 Le problème en une phrase

Méridian confond encore **ce qui existe dans l'entreprise**, **ce qui le représente**, **ce qui le découvre** et **ce qui le prouve**. Cette confusion n'est pas cosmétique : elle produit des faux négatifs (« cette application n'existe pas » alors qu'un dépôt existe), des fusions impossibles à défaire, des réponses non auditables, et des fuites inter-tenant potentielles.

### 1.2 Les six confusions actuelles, et où elles vivent

| Confusion | Constat dans le code | Conséquence |
|---|---|---|
| **Application = Twin** | La table `jumeau` porte le nom, le domaine, la mission et l'équipe. Il n'existe pas de table `application`. Un « jumeau » est à la fois l'entité métier et l'agent. | On ne peut ni renommer une Application sans toucher son Twin, ni fusionner deux Twins sans perdre l'identité, ni distinguer une Application confirmée d'une représentation provisoire. |
| **Twin = processus de découverte** | `jumeau/gardien.py` exécute `veiller(jumeau_id)` : une passe de découverte est attachée à un Twin, sans objet `DiscoveryRun`. | Une panne de découverte ressemble à une panne du Twin. On ne peut ni rejouer une découverte, ni la facturer, ni prouver ce qui a été observé à une date donnée. |
| **SourceArtifact = Application** | `jumeau/registre.py` projette `sources_detail` et `reel` comme des attributs d'application. La version de travail de `flore.application_nommee` reconnaissait un dépôt comme nom d'application ; ce correctif a été retiré au profit de `identite.resoudre` (source → twin → application candidate). | Un dépôt, un mock ou un fork ne doit plus être pris pour une Application ; un renommage de dépôt ne casse plus la résolution. |
| **Assertion = vérité** | Les Claims portent `statut`, `maturite`, `confiance`, mais pas de **mode d'assertion** explicite (`déclaré`, `observé`, `inféré`) distinct de la vérification. | Une inférence du modèle et une observation déterministe se ressemblent à l'écran. On ne sait pas si une phrase vient d'un contrat OpenAPI, d'une route de code ou d'une supposition. |
| **Interface = Claim** | `EXPOSE` est une chaîne de caractères. Il n'existe ni `Interface`, ni `Operation`, ni `Binding`, ni version de contrat. | Les ruptures de contrat sont invisibles. On ne peut pas savoir qui consomme quelle opération, ni quelle version est déclarée, observée ou seulement inférée. |
| **Tenant = espace/persona** | `tenant_id` existe sur certaines tables, mais les requêtes et la projection Mongo sont globales. `X-Persona` et `X-Espace` sont des contextes d'usage, pas une frontière de sécurité. | Les tests d'isolation ne peuvent pas être exhaustifs. Un identifiant deviné peut traverser un tenant. Les caches, prompts, logs et métriques ne sont pas naturellement cloisonnés. |

Deux fondations récentes vont dans le bon sens et ne sont pas à jeter : `backend/jumeau/identite.py` distingue déjà une mention de dépôt d'un nom d'application et rend un chemin `source → twin → application candidate` ; `backend/jumeau/interfaces.py` distingue déjà une assertion `declared` d'une observation et retire les secrets d'URL. Elles restent incomplètes : pas d'entité `Application`, l'identifiant de la candidate est encore celui du Twin, pas de `ResolutionCase` persistant, pas de promotion, pas de version d'interface ni de binding `OBSERVED`. Le programme les étend, il ne les remplace pas.

**Constat complémentaire, non complaisant.** La version de travail de `flore.application_nommee` ajoutait les noms de dépôts comme alias d'application, avec le test `test_application_nommee_par_le_depot_source`. C'est exactement l'anti-pattern que l'ADR-0001 rejette ; l'alias et le test ont été retirés. `identite.resoudre` produit désormais le chemin `SourceArtifact(repo:gsf-mockup) → Twin(nouveau-jumeau, provisoire) → Application candidate`, et le serveur l'utilise.

### 1.3 Conséquences opérationnelles

- **Faux négatifs.** Une question sur un dépôt non encore ingéré reçoit « je ne connais pas » alors qu'un artefact existe. La bonne réponse est « non observé dans tel périmètre, à telle date », avec la source et la prochaine vérification.
- **Fausses fusions.** Deux Twins issus du même dépôt, ou deux Applications homonymes dans deux domaines, peuvent être fusionnés sur une ressemblance de nom. Une fusion non réversible est un incident de confiance.
- **Audit impossible.** Sans `ResolutionCase`, sans `PromotionRecord`, sans autorité ni signature, on ne peut pas expliquer pourquoi une Application est canonique. La réponse « c'est dans la base » n'est pas un audit.
- **Dérive des interfaces.** Une route retirée, un champ obligatoire ajouté, un consommateur oublié : rien ne le signale si l'interface reste une phrase dans un Claim.
- **Risque multi-tenant.** Une projection Mongo globale, un cache non préfixé ou un prompt qui mélange deux tenants sont des fuites, même sans intention malveillante.
- **Coût.** Un agent par connecteur, ou une découverte relancée à chaque question, multiplie les appels modèle sans améliorer la preuve.

### 1.4 Invariants

Les invariants suivants sont normatifs. Ils doivent être testés au niveau unitaire, d'intégration, ou par le jeu d'or.

| # | Invariant | Test d'acceptation |
|---|---|---|
**Précision de vocabulaire.** « Application est la seule identité métier canonique » signifie que le **type** Application est le seul type d'entité métier qui peut devenir canonique. Une instance d'Application peut être à l'état `CANDIDATE` (non canonique) ou `CONFIRMED` (canonique au sens fort). Aucun autre type — Twin, SourceArtifact, DiscoveryRun, Interface — ne peut devenir une Application par promotion.

| **I01** | **Application est la seule identité métier canonique.** Un `Twin`, un `SourceArtifact`, un `DiscoveryRun`, un `Finding`, un `Claim`, une `Interface` ne sont jamais une Application. | Un test d'architecture refuse toute FK nommée `application_id` pointant vers `source_artifact`, `discovery_run` ou `twin`. |
| **I02** | **Twin est une représentation durable, pas un processus.** Il peut être provisoire, mais il a une identité stable, un cycle de vie et des artefacts liés. | Un Twin peut être créé sans `DiscoveryRun` (création humaine), et un `DiscoveryRun` peut produire zéro Twin. |
| **I03** | **DiscoveryRun/Gardien est un processus.** Chaque découverte est une exécution avec état, curseur, coût, erreurs, et journal. | Aucune écriture d'identité ne se produit hors d'un `DiscoveryRun` ou d'une décision humaine/registre signé. |
| **I04** | **SourceArtifact n'est jamais une Application.** Un dépôt, un fichier de configuration, un document, un ticket, un schéma ou une preuve reste un artefact. | Un artefact peut être lié à plusieurs Twins ; aucun écran ne le présente comme une Application. |
| **I05** | **Aucun nom de dépôt n'est un alias d'Application.** Le résolveur applicatif ne lit jamais `source_artifact` et ne contient aucune règle du type `git-… → application`. | Test d'architecture : `identite/resolveur` n'importe pas `artefacts` et ne contient aucune référence à `repo`, `git-` ou `source_artifact`. |
| **I06** | **Toute assertion porte son mode, sa provenance, sa fraîcheur et sa confiance.** | Toute ligne d'assertion a `mode ∈ {DECLARED, OBSERVED, INFERRED}`, `provenance`, `observed_at`, `confidence`. |
| **I07** | **Aucune négation sans ResolutionCase.** Une absence n'est jamais une preuve d'absence : elle est « non observé ». | Toute réponse négative référence un `resolution_case_id` avec périmètre, sources interrogées, date et couverture. |
| **I08** | **Une source indisponible rend la résolution inconclusive, pas négative.** | Si une source requise échoue, l'issue est `INCONCLUSIVE`, jamais `NOT_OBSERVED`. |
| **I09** | **Twin provisoire peut répondre, mais avec identité marquée et proposition de nomination/promotion.** | La réponse contient `kind=TWIN_PROVISIONAL`, le libellé provisoire, l'Application candidate, les sources, la fraîcheur, les actions. |
| **I10** | **Aucune promotion automatique sur un dépôt, un mock, un README, un score de maturité ou une confiance LLM.** | Test de non-régression : aucun événement de promotion n'est émis par un `DiscoveryRun`, un parser ou un agent. |
| **I11** | **La promotion canonique est humaine ou signée par un registre externe autoritatif.** | Toute transition vers `CONFIRMED` possède un `PromotionRecord` avec autorité, acteur, preuve et audit. |
| **I12** | **Les interfaces sont des contrats versionnés, avec opérations et bindings.** | Une interface sans version, sans opération ou sans binding n'est pas publiable. |
| **I13** | **Les connecteurs sont déterministes, par système source ; les parseurs sont par format ; il n'y a pas un agent par connecteur.** | Les tests de connecteur sont reproductibles sans modèle ; un connecteur ne contient aucun appel LLM. |
| **I14** | **Le tenant est la frontière de sécurité supérieure.** Tout objet, requête, cache, prompt, log, métrique, artefact, secret et événement d'audit est tenant-scopé. | Tests d'isolation sur API, stores, recherche, cache, vecteurs, prompts, logs et métriques. |
| **I15** | **Les secrets ne sont que des références.** Aucun secret dans un artefact, un prompt, un log, une URL, une erreur ou une métrique. | Scan de secrets sur les artefacts, prompts, logs et traces ; zéro occurrence. |
| **I16** | **L'audit est append-only et infalsifiable.** | Toute tentative de mise à jour ou suppression d'un événement d'audit échoue ; la chaîne de hachage est vérifiable. |
| **I17** | **Les relations du Mesh sont dérivées, jamais éditées directement.** | Aucun endpoint d'écriture directe d'une relation ; toute relation possède sa dérivation et sa provenance. |
| **I18** | **Les fusions et renommages sont réversibles.** | Une fusion peut être scindée ; un renommage conserve `application_id` ; aucune suppression définitive de preuve ou d'audit. |
| **I19** | **Le LLM propose ; il ne valide pas, ne fusionne pas, ne promeut pas, ne déclare pas une absence.** | Les sorties du modèle sont des `PROPOSED` ou des `INFERRED` ; aucune transition canonique n'est déclenchée par un modèle seul. |
| **I20** | **Toute preuve périmée est signalée comme telle.** | Une réponse fondée sur une preuve dont `valid_until` est dépassé porte la mention « périmé » et ne peut pas être présentée comme courante. |
| **I21** | **Toute modification du résolveur, de la promotion, des connecteurs ou de la politique tenant passe le jeu d'or.** | Le gate CI échoue si le jeu d'or identité/sécurité n'est pas au vert. |

### 1.5 Vocabulaire normatif

#### 1.5.1 Identité et découverte

| Terme | Définition | Ce que ce n'est pas |
|---|---|---|
| **Application** | Entité métier canonique et durable : une application logicielle avec un identifiant stable, un nom canonique, des alias autoritatifs, des identifiants externes, un propriétaire, un domaine et un cycle de vie. | Un Twin, un dépôt, un mock, un document, un run de découverte. |
| **Application candidate** | Une `Application` à l'état `CANDIDATE` : proposition argumentée, non canonique, qui peut être promue ou rejetée. | Une Application confirmée ; un alias actif ; une preuve de production. |
| **Twin** | Représentation numérique durable d'une Application ou d'une Application candidate, et agent associé. Il porte des Claims, des preuves, une fiche, des artefacts liés, et il peut répondre. | L'Application elle-même ; un processus ; un dépôt ; un run. |
| **Twin provisoire** | Twin créé à partir d'un ou plusieurs artefacts, avant qu'une Application soit confirmée. Il peut être lié à une Application candidate ou n'en avoir aucune. Il est durable, répondant, mais son identité est marquée `PROVISIONAL`. | Un brouillon jetable ; une Application candidate ; une promotion implicite. |
| **DiscoveryRun** | Exécution datée et bornée d'une découverte : périmètre, sources, curseur, findings, coût, erreurs. | Un Twin ; une Application ; un état permanent. |
| **Gardien** | Composant qui planifie, déclenche et exécute les `DiscoveryRun` selon les politiques (webhook, polling, manuel). | Une identité ; un Twin ; un agent par connecteur. |
| **SourceArtifact** | Dépôt, fichier de configuration, contrat, document, ticket, schéma, incident, preuve : une unité versionnée observée depuis un système source. | Une Application ; un alias ; une identité métier. |
| **Connector** | Adaptateur déterministe et en lecture seule vers un système source (GitHub, Confluence, Jira, ServiceNow, Datadog, CMDB, base de données). | Un agent ; un interpréteur ; un décideur d'identité. |
| **Parser** | Composant déterministe qui transforme un artefact d'un format donné (Maven, npm, OpenAPI, Protobuf, Dockerfile, Kubernetes, Terraform, SQL, CI) en objets typés. | Un modèle de langage ; un connector. |
| **ResolutionCase** | Dossier qui enregistre une requête de résolution, ses candidats, ses preuves, son périmètre, son issue et sa décision. | Une réponse de chat ; une supposition ; un cache. |
| **PromotionRecord** | Décision datée et auditée qui fait passer une Application de `CANDIDATE` à `CONFIRMED`, ou qui fusionne/scinde des identités. | Une écriture de dépôt ; une réponse de modèle ; une auto-validation. |

**Twin durable, agent éphémère.** Le Twin est l'objet persistant (identité, artefacts, Claims, fiche). L'agent est une instance d'exécution construite à la demande, avec un contexte borné, des outils et un budget. Le runtime de l'agent n'est pas le Twin ; il ne peut ni promouvoir, ni fusionner, ni écrire l'identité.

#### 1.5.2 Connaissance, interfaces et Mesh

| Terme | Définition | Ce que ce n'est pas |
|---|---|---|
| **Assertion** | Énoncé typé sur un sujet (Application, Twin, artefact, interface, opération, binding), avec mode, provenance, fraîcheur, confiance et état de vérification. | Une vérité par défaut ; une phrase sans source. |
| **Evidence** | Preuve immuable pointant vers une version d'artefact et un locator (fichier + lignes, page + version, ticket + révision), avec hash. | Le contenu brut non versionné ; une opinion. |
| **Interface** | Contrat versionné exposé ou consommé par une Application : protocole, nom, version, spécification, cycle de vie. | Un Claim `EXPOSE` en texte libre. |
| **Operation** | Opération d'une Interface : méthode et chemin, topic, RPC ou requête, avec schémas, auth, idempotence et effets de bord. | Une route non versionnée ; un simple nom de service. |
| **Binding** | Lien assertionnel entre une Operation et une implémentation, une configuration, un déploiement, un appel client ou une observation runtime. | Une relation directe non prouvée ; une déduction unique. |
| **MeshRelation** | Relation dérivée entre Applications (dépendance, appel, consommation, appartenance), avec état, provenance et fraîcheur. | Une arête éditée à la main ; une vérité sans preuve. |
| **Tenant** | Frontière de sécurité et de données : une organisation cliente, avec ses identités, ses objets, ses secrets et son audit. | Un espace de travail ; une persona ; un filtre d'interface. |

Un `SourceArtifact` peut servir de preuve ; l'`Evidence` est l'enregistrement immuable qui pointe vers sa version et son locator. Un artefact n'est pas une Application ; une preuve n'est pas une identité.

### 1.6 Modèle de vérité : quatre axes orthogonaux

Méridian ne doit pas confondre **d'où vient une assertion**, **si elle est vérifiée**, **quelle est sa maturité** et **si elle est fraîche**. Ces quatre axes sont indépendants.

| Axe | Valeurs | Question à laquelle il répond | Ne doit pas être confondu avec |
|---|---|---|---|
| **Mode** | `DECLARED`, `OBSERVED`, `INFERRED` | D'où vient l'assertion ? D'un contrat/document, d'une observation déterministe, ou d'une inférence ? | La vérité ; la confiance ; la maturité. |
| **Vérification** | `EN_ATTENTE`, `VERIFIE`, `RECOUPE`, `SELON`, `CONTESTE`, `EN_PARTIE`, `NON_APPUYE`, `INCERTAIN` | La preuve soutient-elle l'énoncé ? | Le mode ; le statut de gouvernance. |
| **Maturité** | `M1` à `M4`/`M5` (échelle existante) | Quelle est la force et l'indépendance des preuves ? | La confiance du modèle ; le nombre de sources. |
| **Fraîcheur** | `observed_at`, `valid_until`, `source_version`, `stale` | L'assertion est-elle encore valable à cette version ? | La date de création du Claim. |

Les jetons `DECLARED`, `OBSERVED`, `INFERRED` sont normatifs dans le code et l'API ; les libellés français sont **déclaré**, **observé**, **inféré**.

**Exemple.** Une route `GET /payments` dans un fichier OpenAPI est `DECLARED` (le contrat le dit), `VERIFIE` (le parseur a lu la ligne), `M2` (une preuve), et fraîche au SHA courant. La même route dans un décorateur de code est `OBSERVED`, `RECOUPE` si le parseur de code et le contrat concordent, `M3` si deux systèmes indépendants concordent. Une phrase du modèle « cette application consomme probablement Payments » est `INFERRED`, `EN_ATTENTE`, `M1`, et ne doit jamais être présentée comme un binding vérifié.

### 1.7 Résolution d'identité

#### 1.7.1 Deux composants, jamais un seul

| Composant | Entrées | Sorties | Interdictions |
|---|---|---|---|
| **ApplicationResolver** | Identifiant canonique, alias actif, identifiant externe autoritatif, nom canonique, candidats par similarité. | `Application` canonique, ou candidats (dont `Application` candidate) à examiner, ou `AMBIGUOUS`, `NOT_OBSERVED`/`INCONCLUSIVE` avec `ResolutionCase`. | Ne lit jamais `source_artifact` ; ne contient aucun nom de dépôt ; ne décide jamais sur une similarité seule. |
| **ArtifactRouter** | Référence d'artefact : dépôt, chemin, URL, tag de service, identifiant de configuration. | `SourceArtifact` + `Twin` lié (provisoire ou actif) + Application éventuelle. | Ne crée jamais un alias d'Application ; ne promeut jamais ; ne confond pas un artefact avec une Application. |
| **AnswerComposer** | Résultat du résolveur, du routeur, des Twins et des preuves. | Réponse avec identité marquée, preuves, fraîcheur, actions. | Ne choisit pas silencieusement entre deux candidats ; ne dit jamais « n'existe pas ». |

**Règle structurante.** `gsf-mockup` n'est pas une entrée du résolveur applicatif. C'est une entrée du routeur d'artefacts. Le résolveur ne connaît que des noms métier, des alias autoritatifs et des identifiants externes. Le routeur connaît les dépôts, les fichiers et les configurations. Cette séparation est testée par architecture : le module de résolution ne doit pas importer le module d'artefacts.

#### 1.7.2 Ordre déterministe

1. **Identifiant externe autoritatif** (CMDB, catalogue de services) actif et non expiré → Application canonique.
2. **Alias actif** ou nom canonique exact, avec autorité `HUMAN` ou `EXTERNAL_REGISTRY` → Application canonique.
3. **Référence d'artefact exacte** → `ArtifactRouter` → Twin provisoire ou actif.
4. **Identifiant externe non autoritatif** (tag Datadog, nom de service, URL) → candidat, jamais décision.
5. **Similarité de nom ou embedding** → candidats uniquement, avec score, jamais décision.
6. **Aucun candidat** → `ResolutionCase` avec issue `NOT_OBSERVED` si toutes les sources requises ont répondu, sinon `INCONCLUSIVE`.

Une similarité ne peut jamais produire une fusion, une promotion ou une réponse canonique. Elle produit une liste de candidats à examiner. Si l'entrée porte une syntaxe d'artefact explicite (URL, `org/repo`, chemin, préfixe `repo:`), le routeur d'artefacts est prioritaire ; si elle peut aussi se lire comme un nom métier, l'ambiguïté est exposée, jamais tranchée silencieusement.

#### 1.7.3 Issues de résolution

| Issue | Sens | Réponse autorisée | Réponse interdite |
|---|---|---|---|
| `RESOLVED_CANONICAL` | Une Application `CONFIRMED` est identifiée. | Réponse canonique, avec alias et identifiants externes. | — |
| `RESOLVED_PROVISIONAL` | Un Twin provisoire est identifié ; aucune Application confirmée. | Réponse marquée `PROVISIONAL`, avec candidat et actions. | « Je suis l'Application X » ; promotion implicite. |
| `ARTIFACT_ONLY` | Un artefact existe, aucun Twin n'est encore lié. | Décrire l'artefact, proposer de créer un Twin ou de lancer une découverte. | Appeler l'artefact « application ». |
| `AMBIGUOUS` | Plusieurs candidats plausibles. | Lister les candidats, demander une précision, ne rien fusionner. | Choisir le premier ; fusionner. |
| `NOT_OBSERVED` | Toutes les sources requises ont répondu, aucun candidat. | « Non observé dans [périmètre] au [date] », avec sources et couverture. | « N'existe pas » ; « absent » sans périmètre. |
| `INCONCLUSIVE` | Une source requise a échoué ou le périmètre est incomplet. | « Je ne peux pas conclure : [source] indisponible ; prochaine vérification… ». | Toute formulation négative. |
| `REJECTED` | Un candidat a été explicitement rejeté par une autorité. | « Rejeté par [autorité] le [date], motif… ». | Le présenter comme inexistant. |

#### 1.7.4 Contrat du « non observé »

Le `ResolutionCase` est le **registre de résolution** : sans lui, aucune négation n'est prononcée. Un `NOT_OBSERVED` n'est pas une vérité négative. C'est une **observation bornée**. Il DOIT porter :

- `scope` : tenant, systèmes sources, types d'artefacts, fenêtre temporelle ;
- `sources_ok` et `sources_failed` ;
- `coverage` : ce qui a été réellement interrogé ;
- `queried_at` et `valid_until` ;
- `case_id` et `next_check` ;
- `wording` : « Non observé dans [scope] au [date]. Ce n'est pas une preuve d'absence. »

Si aucune `ResolutionCase` n'existe, l'orchestrateur NE DOIT PAS dire « non observé » ni « n'existe pas ». Il dit : « Je n'ai pas encore de résolution pour ce nom ; je peux lancer une recherche dans [périmètre]. »

#### 1.7.5 Règle sur les noms de dépôts

La forme canonique d'une référence d'artefact est `{system}:{org}/{name}` (par exemple `github:org/gsf-mockup`) ; `repo:gsf-mockup` est une notation courte de ce document.

- Un nom de dépôt est un `SourceArtifact.external_ref`. Il peut être un **libellé provisoire** de Twin et un **nom proposé** pour une Application candidate.
- Il n'est **jamais** un `ApplicationAlias`, même après promotion.
- Si l'organisation veut utiliser ce nom comme nom métier, c'est une décision humaine distincte, justifiée comme nom métier, pas comme dépôt. Le nom de dépôt reste l'artefact ; le résolveur ne reçoit que le nom canonique décidé, et la chaîne de dépôt reste traitée par le routeur.
- Le prompt de Flore DOIT dire : « Si l'interlocuteur nomme un dépôt, route vers l'artefact puis le Twin ; ne traite jamais ce nom comme un alias d'Application. »
- Le test `test_application_nommee_par_le_depot_source` a été supprimé ; `test_identite.py` couvre le routeur d'artefacts.

### 1.8 Contrat de réponse d'un Twin provisoire

Un Twin provisoire peut répondre. Il ne peut pas se faire passer pour une Application canonique.

| Élément de réponse | Contenu obligatoire |
|---|---|
| `identite.kind` | `TWIN_PROVISIONAL` |
| `identite.twin_id` | Identifiant stable du Twin |
| `identite.label` | Libellé provisoire (par exemple `nouveau-jumeau`) |
| `identite.proposed_application_name` | Nom proposé pour l'Application candidate, marqué comme proposition |
| `identite.application_candidate_id` | Identifiant de l'Application candidate, ou `null` |
| `identite.application_state` | `CANDIDATE` si une candidate existe, sinon `NONE` |
| `identite.sources` | Artefacts liés, avec version et locator |
| `identite.freshness` | Date d'observation, version de source, état périmé ou non |
| `identite.confidence` | Confiance et méthode |
| `identite.actions` | `nommer`, `rattacher_à_une_application`, `rejeter`, `lancer_une_découverte`, `voir_les_preuves` |
| `identite.promotion` | Un objet `promotion_request` possible, jamais une promotion appliquée |

**Formulation autorisée (exemple).** « Identité provisoire : Twin `nouveau-jumeau`, lié au dépôt `gsf-mockup` au commit `…`; Application candidate `app-…` (non confirmée). Voici ce que le code et la configuration montrent… Pour rendre cette Application canonique, un propriétaire habilité peut ouvrir une demande de promotion ; la décision sera auditée. »

**Formulations interdites.** « Je suis l'Application GSF. » — « Cette Application n'existe pas. » — « La promotion est faite. » — « Ce dépôt est une Application. »

### 1.9 Ce que ce programme ne fait pas

- Il ne promeut aucune Application sans autorité humaine ou registre externe signé.
- Il ne transforme pas un dépôt, un mock ou un README en preuve de production.
- Il ne crée pas un agent par connecteur.
- Il n'écrit pas dans les systèmes sources.
- Il ne fusionne pas deux identités sans décision humaine ou registre signé.
- Il ne remplace pas le moteur de Situations ; il lui fournit une identité et des relations fiables.

---

## 2. Architecture cible en couches

### 2.1 Vue d'ensemble

```text
Sources (GitHub, Confluence, Jira, ServiceNow/CMDB, Datadog, schémas)
  └─► Connecteurs (déterministes, lecture seule)
        └─► SourceArtifact (version, hash, locator)
              └─► DiscoveryRun / Gardien (runs, curseurs, findings, coûts)
                    ├─► ResolutionCase ─► Application (CANDIDATE / CONFIRMED) ─► Promotion
                    │                                      ▲
                    └─► Twin (PROVISIONAL / ACTIVE) ───────┘ lien
                          └─► Interfaces (contrats, opérations, bindings)
                                └─► Mesh (relations dérivées)
                                      └─► Orchestrateur (Flore : routage, réponse, action)

L'orchestrateur lit Application, Twin, Interfaces et Mesh ; il ne décide jamais de l'identité.
Transverse : Tenant & Sécurité · Audit · Évaluation · Observabilité & Coût
```

Le flux est volontairement unidirectionnel pour l'identité : **les artefacts alimentent la découverte ; la découverte peut créer un Twin provisoire et une Application candidate ; la résolution et la promotion transforment la candidate en identité confirmée ; l'identité confirmée autorise la représentation canonique ; la représentation expose des interfaces ; les interfaces alimentent le Mesh ; l'orchestrateur répond.** Un Twin provisoire peut donc précéder l'identité confirmée, mais il ne peut jamais la remplacer. Aucun retour d'un modèle ou d'un run ne peut écrire directement une identité canonique.

### 2.2 Responsabilités des couches

| Couche | Responsabilité | Composants | Possède | Ne fait jamais | Phase |
|---|---|---|---|---|---|
| **Identité** | Définir ce qui existe canoniquement. | `Application`, alias, identifiants externes, cycle de vie, `PromotionRecord`. | La vérité d'identité et sa décision. | Créer une Application depuis un dépôt ; promouvoir sans autorité. | 0–1 |
| **Résolution** | Transformer une mention, un identifiant ou un artefact en résultat d'identité borné. | `ApplicationResolver`, `ArtifactRouter`, `ResolutionCase`, assertions, issues. | Les dossiers de résolution et leurs preuves. | Choisir un candidat par similarité ; nier sans dossier. | 0–1 |
| **Twin / Discovery** | Entretenir la représentation et exécuter la découverte perpétuelle. | `Twin`, cycle de vie, agent, `DiscoveryRun`, `Gardien`, `Finding`. | Les Twins, les runs, les findings, les fiches. | Décider de l'identité canonique ; fusionner sans humain. | 1–3 |
| **Interfaces** | Décrire les contrats, opérations et liens d'implémentation. | `Interface`, `Operation`, `Binding`, conflits, diff de versions. | Les contrats versionnés et les bindings. | Remplacer une preuve par une phrase de modèle. | 1–3 |
| **Connecteurs & artefacts** | Lire les systèmes sources, versionner les artefacts, parser les formats. | `SourceSystem`, `Connector`, `Parser`, `SourceArtifact`, curseurs, quarantaine. | Les artefacts, versions, hashes, locators. | Interpréter une identité ; écrire dans la source ; appeler un LLM. | 0–2 |
| **Mesh** | Projeter les relations entre Applications à partir des preuves. | `MeshRelation`, projection, états, fraîcheur. | Le graphe dérivé. | Être édité directement ; traverser un tenant. | 2–3 |
| **Orchestrateur** | Router, mobiliser les Twins, composer une réponse et des actions. | Flore, routeur, composeur de réponse, outils bornés. | Les réponses et les demandes d'action. | Promouvoir ; inventer une identité ; conclure à l'absence. | 1–3 |
| **Sécurité** | Garantir tenant, secrets, audit, lecture seule, redaction. | Contexte tenant, RBAC/ABAC, coffre de secrets, audit, politiques connecteurs. | Les décisions d'accès et les traces. | Laisser passer une requête sans tenant ; exposer un secret. | 0–3 |
| **Évaluation** | Mesurer la qualité réelle et bloquer les régressions. | Jeu d'or, harnais, juges calibrés, métriques, gates. | Les mesures et les seuils. | S'auto-noter avec le même modèle qui produit la réponse. | 0–3 |

### 2.3 Stores et source de vérité

| Store | Contenu | Autoritatif ? | Règles |
|---|---|---|---|
| **PostgreSQL** | Applications, alias, IDs externes, Twins, artefacts (métadonnées), Claims, preuves, interfaces, runs, résolutions, promotions, audit. | **Oui** pour tous les objets canoniques. | `tenant_id` partout ; RLS ; clés uniques composites ; migrations réversibles ; aucun accès global. |
| **Stockage objet immuable** | Contenus d'artefacts et instantanés, si la politique l'autorise ; hash en base. | Non : c'est une source de preuve, pas d'identité. | Préfixe `tenant/{tenant_id}/` ; chiffrement par tenant ; WORM ou Object Lock si disponible ; rétention. |
| **MongoDB** | Projection UI : Atlas, registre, espaces de travail. | **Non.** Read model reconstructible. | Filtre tenant obligatoire ; `origin` (`REAL`/`DEMO`) ; jamais utilisé pour une décision d'identité. |
| **Redis** | Files, verrous, caches, limites de débit. | Non. | Préfixe `tenant:{tenant_id}:` ; TTL ; pas de secret ; perte acceptable. |
| **Index de code** | Index dérivé des dépôts au SHA. | Non. | Reconstructible ; nommé par tenant/artefact/version ; jamais une identité. |
| **Index vectoriel** | Recherche sémantique, candidats de résolution. | Non. | Namespace par tenant ; candidats uniquement ; jamais une décision. |
| **Journal d'événements / outbox** | Intégration asynchrone, rejeu. | Non pour l'état courant. | Enveloppe tenant ; idempotence ; pas de secrets ; DLQ. |

**Règle.** Une projection (Mongo, cache, index) ne peut jamais contredire Postgres. En cas d'écart, Postgres gagne, la projection est reconstruite, et l'écart est audité.

### 2.4 Modèle d'événements

| Événement | Producteur | Consommateurs | Clé d'idempotence | Notes |
|---|---|---|---|---|
| `artifact.observed` | Connecteur | Registre, découverte | `tenant + system + ref + version` | Contient le hash, pas le contenu si sensible. |
| `discovery.run.started` | Gardien | Observabilité, UI | `run_id` | Inclut le périmètre et le budget. |
| `discovery.run.finished` | Gardien | Résolution, Twin, UI | `run_id` | `SUCCEEDED`, `PARTIAL`, `FAILED`, `CANCELLED`, `ORPHANED`. |
| `twin.provisioned` | Twin | UI, résolution | `twin_id` | Jamais un événement de promotion. |
| `resolution.proposed` | Résolution | UI, audit | `case_id + revision` | Candidats et preuves. |
| `resolution.decided` | Résolution | Identité, UI, audit | `case_id + decision_id` | Décision humaine ou registre. |
| `promotion.requested` | Promotion | UI, notifications | `request_id` | Demande, pas décision. |
| `promotion.applied` | Promotion | Identité, Twin, audit | `promotion_id` | Transition atomique + audit. |
| `interface.version.published` | Interfaces | Mesh, UI | `interface_id + version` | Version immuable. |
| `binding.changed` | Interfaces | Mesh, qualité | `binding_id + revision` | Déclenche la revalidation. |
| `mesh.relation.updated` | Mesh | UI, Situations | `relation_id + revision` | Dérivée, jamais éditée. |
| `answer.served` | Orchestrateur | Qualité, audit | `request_id` | Identité, preuves, fraîcheur, coût. |
| `tenant.policy.changed` | Sécurité | Tous | `tenant_id + policy_version` | Invalide les caches. |

Les événements sont publiés par **outbox transactionnel** : l'écriture métier et l'événement sont dans la même transaction. Les consommateurs sont idempotents. Un événement ne contient jamais de secret ni de contenu classifié non redacté.

### 2.5 Contrats d'API

Toutes les routes sont préfixées par `/api`. Le tenant vient de l'identité authentifiée, jamais du corps de la requête ni d'un en-tête libre. Les POST acceptent `Idempotency-Key`. Les décisions acceptent `If-Match` (ETag) pour éviter les courses.

| Endpoint | Rôle | Autorisation | Idempotence | Réponse |
|---|---|---|---|---|
| `POST /api/identity/resolutions` | Lancer une résolution applicative. | `VIEWER` sur le tenant. | Oui | `ResolutionCase` avec issue. |
| `GET /api/identity/resolutions/{id}` | Lire un dossier de résolution. | `VIEWER`, tenant. | — | Case, assertions, décision. |
| `POST /api/identity/resolutions/{id}/decisions` | Trancher un cas ambigu ou candidat. | `APPLICATION_OWNER` ou `PORTFOLIO_OWNER`, selon la décision. | Oui | Décision auditée. |
| `POST /api/artifacts/resolve` | Router une référence d'artefact. | `VIEWER`, tenant. | Oui | Artefact + Twin + Application éventuelle. |
| `GET /api/artifacts/{id}` | Lire un artefact et ses versions. | `VIEWER`, tenant. | — | Métadonnées, locator, hash, état. |
| `POST /api/discovery/runs` | Déclencher une découverte bornée. | `MAINTAINER` ou service. | Oui | `run_id`, état, budget. |
| `GET /api/discovery/runs/{id}` | Suivre une découverte. | `VIEWER`, tenant. | — | État, curseur, findings, coût. |
| `GET /api/twins/{id}` | Lire un Twin et son identité. | `VIEWER`, tenant. | — | Twin, identité, artefacts, claims. |
| `POST /api/twins/{id}/promotion-requests` | Proposer une nomination/promotion. | `MAINTAINER` ou `APPLICATION_OWNER`. | Oui | `PromotionRequest` `PENDING`, jamais appliquée. |
| `POST /api/promotion-requests/{id}/decisions` | Approuver ou rejeter. | `APPLICATION_OWNER`/`PORTFOLIO_OWNER` ; quatre yeux pour les opérations destructives. | Oui | `PromotionRecord` + transition. |
| `GET /api/applications/{id}` | Lire l'Application canonique. | `VIEWER`, tenant. | — | Identité, alias, IDs, cycle de vie. |
| `GET /api/interfaces/{id}` | Lire une interface et ses versions. | `VIEWER`, tenant. | — | Contrat, opérations, bindings, conflits. |
| `POST /api/interfaces/{id}/versions` | Publier une version de contrat. | `MAINTAINER`, service parser. | Oui | Version immuable, diff, ruptures. |
| `GET /api/mesh` | Lire le Mesh du tenant. | `VIEWER`, tenant. | — | Applications, relations, états. |
| `GET /api/audit/events` | Lire l'audit. | `AUDITOR` ou admin tenant. | — | Événements paginés, hash chain. |

**Interdits d'API.** Aucun endpoint ne crée directement une Application canonique depuis un dépôt. Aucun endpoint n'écrit dans un système source. Aucun endpoint ne fusionne deux Applications sans `PromotionRequest` et décision. Aucun endpoint ne renvoie un objet d'un autre tenant : un identifiant hors tenant donne `404`, pas `403`.

### 2.6 Compatibilité avec l'existant

| Module existant | Rôle actuel | Rôle cible | Adaptateur / migration |
|---|---|---|---|
| `backend/jumeau/depot.py` | Persistance des jumeaux, preuves, Claims. | Persistance des preuves et Claims, rattachés à un `Twin` ou à une entité typée. | Ajouter `subject_type`/`subject_id` ; conserver `jumeau_id` en compatibilité. |
| `backend/jumeau/registre.py` | Projection Mongo des jumeaux réels. | Projection UI des Applications/Twins, avec marque d'identité. | Ajouter `identity_kind`, `identity_mark`, `application_id`, `candidate_id`, `tenant_id`, `origin`. |
| `backend/jumeau/flore.py` | Réponse et routage ; l'alias de dépôt a été retiré. | `server.generer_reponse_flore` appelle `identite.resoudre`, puis consulte le twin. | La résolution typée est intégrée ; l'Application canonique distincte reste à persister. |
| `backend/jumeau/mobilisation.py` | Cartes et mobilisation multi-Twins. | Même rôle, avec identité marquée et cartes séparant nom métier et artefacts. | Ajouter le bandeau d'identité ; retirer l'instruction « nommer par le dépôt ». |
| `backend/jumeau/naissance.py` | Crée un jumeau directement depuis une commande. | Crée un **Twin provisoire** et un `DiscoveryRun` ; ne crée jamais une Application canonique. | Le nom saisi devient un libellé provisoire ; la promotion reste humaine. |
| `backend/jumeau/gardien.py` | Passe de découverte par `jumeau_id`. | Exécuteur de `DiscoveryRun` ; le Twin n'est qu'un périmètre possible. | Déplacer vers `decouverte/gardien.py` en phase 2 ; conserver une façade. |
| `backend/jumeau/schema.sql` | Tables `jumeau`, `source`, `claim`, etc. | Tables historiques maintenues pendant la migration. | Nouveau `002_identite.sql` ; double écriture ; backfill ; feature flag. |
| `backend/server.py` | Routes et routage Flore. | Délègue aux services d'identité, d'artefacts, de découverte et de promotion. | Feature flag `IDENTITY_V2` ; routes historiques conservées. |
| `backend/jumeau/schemas.py` | Vérification des schémas Mermaid, états. | Réutilisé pour les états de vérification. | Aucun changement de sens ; les états sont réutilisés dans le modèle de vérité. |
| `backend/jumeau/poignee.py` | Confirmation de relations entre gardiens. | Produit des assertions de relation, pas des écritures directes du Mesh. | Écrire dans `ResolutionAssertion`/`MeshRelation` dérivée. |
| `backend/jumeau/evaluation.py` | Jeu de référence par Twin. | Étendu au jeu d'or identité, typage, interfaces, sécurité. | Nouveau module `evaluation/jeu_or.py` ; conserver l'existant. |
| `backend/jumeau/identite.py` | Fondation de résolution typée : une mention de dépôt produit un chemin `source → twin → application candidate` ; une absence est dite « non prouvée ». | `ApplicationResolver` + `ArtifactRouter` + `ResolutionCase`. | Conserver l'API de résolution ; ajouter la persistance, les issues `NOT_OBSERVED`/`INCONCLUSIVE`, la séparation des deux composants et la promotion. Renommer `absent` en `NOT_OBSERVED` dans l'API. |
| `backend/jumeau/interfaces.py` | Fondation de graphe d'interfaces : parseurs OpenAPI et configuration, assertions `declared`, identifiants stables, secrets d'URL retirés. | `Interface`, `Operation`, `Binding`, version, conflits, persistance. | Conserver les parseurs ; ajouter la persistance, le versionnement, les bindings `OBSERVED`/`INFERRED`, les conflits et le diff de rupture. |

---

## 3. Chantiers numérotés

### 3.0 Vue d'ensemble et ordre

| Chantier | Phase | Dépend de | Sortie principale |
|---|---|---|---|
| **C01** — Vocabulaire et invariant de typage | 0 | — | Les mots et les règles deviennent exécutables. |
| **C02** — Modèle de données identité | 0 | C01 | Schéma typé, tenant-scopé, réversible. |
| **C03** — Résolveur et routeur d'artefacts | 0 | C02 | Résolution déterministe, non-observé borné. |
| **C04** — Connecteurs et registre d'artefacts | 0–1 | C02 | Artefacts versionnés, lecture seule, parsers. |
| **C05** — DiscoveryRun et Gardien | 1 | C03, C04 | Découverte perpétuelle observable. |
| **C06** — Twin provisoire | 1 | C02, C03, C05 | Twin durable, répondant, marqué. |
| **C07** — Promotion canonique | 1 | C02, C06 | Promotion humaine/signée, auditée, réversible. |
| **C08** — Interfaces versionnées | 2 | C04, C06 | Contrats, opérations, bindings, ruptures. |
| **C09** — Mesh dérivé | 2 | C08 | Relations dérivées, jamais éditées. |
| **C10** — Orchestrateur et routage | 1–2 | C03, C06 (C09 en phase 2) | Flore route sans alias de dépôt. |
| **C11** — Sécurité multi-tenant | 0–3 | C02, C04 | Tenant, secrets, audit, lecture seule. |
| **C12** — Jeu d'or et évaluation | 0–3 | C03, C06, C07, C10, C11 | Mesure indépendante et gates. |
| **C13** — Migration, exploitation, coût | 1–3 | C02, C06, C11 | Bascule sans rupture, SLO et budgets. |

---

### C01 — Contrat de vocabulaire et invariant de typage

**Objectif.** Rendre les mots et les séparations exécutables, pour empêcher le retour des confusions dans le code, les API et les prompts.

**Livrables.**
- Glossaire normatif (ce document et l'ADR-0001) ; fiche de revue de conception.
- Types d'identifiants et de sujets : `APPLICATION`, `TWIN`, `SOURCE_ARTIFACT`, `INTERFACE`, `OPERATION`, `BINDING`, `DISCOVERY_RUN`.
- Règles CI : imports interdits (`identite` → `artefacts`), SQL interdit (alias d'Application créé depuis un artefact), tests interdits (nom de dépôt comme alias).
- Table de correspondance `jumeau` historique → `Twin`, et `source` → `SourceArtifact`.
- Modèle de revue : toute PR qui touche l'identité cite l'invariant concerné.

**Dépendances.** Aucune. Ce chantier précède tous les autres.

**Critères d'acceptation.**
- 100 % des nouveaux objets portent `tenant_id` et un type de sujet.
- 0 alias d'Application créé automatiquement depuis un artefact.
- Un test d'architecture échoue si `identite/resolveur` importe `artefacts`.
- Le test `test_application_nommee_par_le_depot_source` est supprimé et remplacé par un test du routeur d'artefacts.
- Les documents et prompts utilisent le vocabulaire normatif ; aucun prompt ne dit qu'une application peut être nommée par son dépôt.

**Métriques.** Violations de règle = 0 ; couverture des invariants par des tests ; délai de revue ; nombre de PR refusées pour ambiguïté de typage.

**Risques.** Résistance au changement de vocabulaire ; coexistence de deux vocabulaires pendant la migration ; dérive des prompts. **Mitigation :** lint de vocabulaire, revue d'architecture, ADR opposable, migration progressive avec alias de compatibilité.

---

### C02 — Modèle de données identité

**Objectif.** Persister le modèle typé avec des contraintes qui rendent les confusions impossibles, et non seulement déconseillées.

**Livrables.**
- Migration `002_identite.sql` : `tenant`, `application`, `application_alias`, `application_external_id`, `twin`, `twin_artifact_link`, `source_system`, `source_artifact`, `discovery_run`, `discovery_finding`, `resolution_case`, `resolution_assertion`, `resolution_decision`, `promotion_request`, `promotion_record`, `interface`, `operation`, `binding`, `binding_conflict`, `mesh_relation`, `audit_event`, `secret_ref`.
- Politiques RLS, clés uniques composites, index de lecture, triggers d'audit.
- ERD, dictionnaire de données, contraintes de suppression.
- Script de backfill et rapport de réconciliation.

**Dépendances.** C01.

**Critères d'acceptation.**
- Toute table métier a `tenant_id` ; toute clé unique inclut le tenant.
- Aucune FK `application_id` ne pointe vers `source_artifact`, `discovery_run` ou `twin`.
- `application_alias.origin` n'accepte que `HUMAN` ou `EXTERNAL_REGISTRY` ; `DISCOVERY` est refusé par contrainte.
- La migration est réversible et rejouable ; zéro orphelin après backfill.
- Les tests RLS prouvent qu'une session tenant A ne lit pas tenant B.

**Métriques.** Durée de migration ; nombre d'orphelins ; couverture des contraintes ; tests RLS au vert ; taille des tables et index.

**Risques.** Conflits avec les données historiques ; verrous de migration ; perte de données. **Mitigation :** tables en ombre, backfill par lots, dry-run, sauvegarde, rollback testé.

---

### C03 — Résolveur applicatif et routeur d'artefacts

**Objectif.** Séparer la résolution d'identité de la résolution d'artefact, et produire des issues bornées au lieu de conclusions non prouvées.

**Livrables.**
- `identite/resolveur` : ordre déterministe, alias autoritatifs, IDs externes, génération de candidats non décisionnelle.
- `artefacts/routeur` : référence d'artefact → `SourceArtifact` → `Twin` → Application éventuelle.
- `ResolutionCase` et `ResolutionDecision` : enregistrement, rejeu, expiration, `supersedes`.
- Logique `NOT_OBSERVED` / `INCONCLUSIVE` avec périmètre, sources, couverture, date.
- API et tests d'architecture.

**Dépendances.** C02.

**Critères d'acceptation.**
- L'ordre de résolution est celui de §1.7.2 ; un ID externe autoritatif gagne sur un alias, qui gagne sur une similarité.
- Le résolveur ne lit jamais `source_artifact` et ne contient aucun nom de dépôt.
- Une mention de dépôt produit un `SourceArtifact` et un `Twin`, jamais un alias d'Application.
- Toute réponse négative référence un `ResolutionCase` ; une source en échec produit `INCONCLUSIVE`.
- Une similarité produit des candidats, jamais une décision.
- Sur le jeu d'or identité : top-1 ≥ 0,95 en phase 1 (cible 0,98 en phase 2) ; fusions erronées = 0.

**Métriques.** Précision top-1 ; rappel ; taux d'abstention ; taux de fausses négations ; latence p95 de résolution.

**Risques.** Faux positifs de similarité ; alias obsolètes ; couverture incomplète. **Mitigation :** seuils conservateurs, abstention, décisions humaines, revue périodique des alias.

---

### C04 — Connecteurs et registre d'artefacts

**Objectif.** Lire les sources de façon déterministe, en lecture seule, avec version, hash, provenance et parseurs par format.

**Livrables.**
- Contrat de connecteur : `discover`, `fetch`, `verify`, `current_version`, `health`.
- Premier connecteur : GitHub (lecture seule, curseur, rate limit, secret ref).
- Registre d'artefacts : `SourceArtifact` versionné, hash, locator, classification, quarantaine.
- Parseurs : manifestes (Maven, npm, Python), OpenAPI/AsyncAPI/Protobuf/GraphQL, routes, configuration, Dockerfile/Kubernetes/Terraform, SQL DDL, CI.
- Tests de contrat avec fixtures ; tests d'idempotence ; tests de sécurité.

**Dépendances.** C02.

**Critères d'acceptation.**
- Un artefact est unique par `(tenant, system, ref, version)` ; un fetch rejoué ne duplique rien.
- Le hash du contenu est stable ; le locator ne contient jamais de secret.
- Le connecteur est en lecture seule : aucun scope d'écriture, aucun `git push`, aucune mutation de la source.
- Les liens symboliques, traversées de chemin, fichiers binaires et secrets sont bloqués ou mis en quarantaine.
- Le parseur est déterministe et versionné ; le curseur reprend après panne.
- Un parseur ne fait aucun appel LLM.

**Métriques.** Couverture des artefacts ; taux de fetch réussi ; précision des parseurs ; secrets détectés = 0 ; latence de curseur.

**Risques.** Limites de débit ; dérive des formats ; monorepos volumineux ; données personnelles. **Mitigation :** backoff, parseurs versionnés, plafonds de taille, redaction, quarantaine.

---

### C05 — DiscoveryRun et Gardien

**Objectif.** Faire de la découverte un processus durable, observable, rejouable et facturable, distinct du Twin.

**Livrables.**
- `decouverte/runs` : création, périmètre, budget, bail, heartbeat, état, findings, coût, erreurs.
- `decouverte/gardien` : planification (webhook, polling, manuel), déclenchement, reprise, backpressure.
- `discovery_finding` : proposition d'artefact, de Twin, de candidat, de relation, de conflit.
- Tableau de bord : runs, fraîcheur, changements, coûts, erreurs.
- Événements outbox et tests de rejeu.

**Dépendances.** C03, C04.

**Critères d'acceptation.**
- Toute action de découverte appartient à un `DiscoveryRun` identifié.
- Un run a un état terminal explicite : `SUCCEEDED`, `PARTIAL`, `FAILED`, `CANCELLED`, `ORPHANED`.
- Un run peut produire zéro Twin ; un Twin peut exister sans run (création humaine) ; aucun run ne promeut une Application.
- Un retry crée un nouveau run avec la même clé d'idempotence, sans dupliquer les findings.
- Une perte de bail produit `ORPHANED`, pas un état silencieusement bloqué.
- Les coûts et volumes sont mesurés par run et par tenant.

**Métriques.** Taux de runs réussis ; latence de détection de changement ; fraîcheur ; coût par run ; runs dupliqués ; backlog de findings.

**Risques.** Runs emballés ; coût modèle ; source indisponible ; duplication de Twins. **Mitigation :** budgets, circuit breaker, leases, déduplication, quarantaine.

---

### C06 — Twin provisoire et réponse marquée

**Objectif.** Faire du Twin provisoire un objet durable, répondant et gouverné, sans jamais le confondre avec une Application canonique.

**Livrables.**
- Provisionnement d'un Twin depuis un cluster d'artefacts (au moins un lien).
- Cycle de vie `PROVISIONAL` → `ACTIVE` / `SUSPENDED` / `MERGED` / `REJECTED` / `RETIRED`.
- `identity_mark`, bandeau de réponse, actions de nomination/rattachement/rejet.
- Lien vers l'Application candidate ; proposition de nom ; proposition de promotion.
- UI : badge provisoire, sources, fraîcheur, bouton « demander la promotion ».
- Tests d'acceptation gsf-mockup.

**Dépendances.** C02, C03, C05.

**Critères d'acceptation.**
- Un Twin provisoire a au moins un artefact lié et un libellé provisoire.
- Il peut répondre, mais toute réponse porte `TWIN_PROVISIONAL` et l'état de l'Application candidate.
- Il ne peut pas employer le nom canonique d'une Application sans le mot « provisoire ».
- Une promotion n'est jamais appliquée par le Twin : il ne peut que créer une `PromotionRequest`.
- Une fusion ou un rejet est une décision humaine, réversible.
- Une source perdue suspend le Twin sans le supprimer.

**Métriques.** Taux de réponses provisoires ; taux de conversion en canonique ; doublons ; temps jusqu'à promotion ; compréhension utilisateur (test qualitatif).

**Risques.** Prolifération de Twins ; confusion UX ; doublons ; perte de confiance. **Mitigation :** déduplication, badges, langage explicite, workflow de fusion, revue périodique.

---

### C07 — Promotion canonique

**Objectif.** Faire de la promotion une décision explicite, autorisée, auditée et réversible, jamais un effet de bord d'un dépôt ou d'un modèle.

**Livrables.**
- `identite/promotion` : demande, décision, application atomique, audit, rollback/split.
- Matrice d'autorité : rôles, quatre yeux, séparation des devoirs.
- Vérificateur de registre externe : issuer allowlist, clé épinglée, signature, expiration, nonce, tenant.
- Déclencheurs interdits codés et testés.
- UI de demande/décision ; notifications ; idempotence.

**Dépendances.** C02, C06.

**Critères d'acceptation.**
- Toute transition vers `CONFIRMED` possède un `PromotionRecord` avec autorité, acteur, preuve, date et audit.
- Auto-promotions = 0 ; aucun événement de promotion n'est émis par un connecteur, un parser, un `DiscoveryRun` ou un LLM.
- Les rôles sont vérifiés ; une opération destructive (fusion, scission, retrait) exige quatre yeux.
- Une signature invalide, expirée ou rejouée est refusée.
- Une promotion est idempotente ; une demande dupliquée renvoie le même résultat.
- Un renommage conserve `application_id` ; une fusion est réversible par scission.

**Métriques.** Précision des promotions ; auto-promotions = 0 ; taux de reversal ; temps jusqu'à promotion ; couverture d'audit.

**Risques.** Goulot humain ; collusion ; compromission de clé ; registre indisponible. **Mitigation :** file de revue, séparation des devoirs, rotation de clés, repli sur candidat.

---

### C08 — Interfaces versionnées

**Objectif.** Remplacer les Claims `EXPOSE` en texte libre par des contrats versionnés, des opérations et des bindings prouvés.

**Livrables.**
- `interfaces/` : `Interface`, `Operation`, `Binding`, `BindingConflict`, version, compatibilité, cycle de vie.
- Parseurs OpenAPI/AsyncAPI/Protobuf/GraphQL ; bindings de routes, configuration, déploiement, appels clients.
- Moteur de diff déterministe : opérations ajoutées/retirées, schémas, champs obligatoires, codes, auth.
- Détection des consommateurs à partir des bindings `CONSUMED`.
- API/UI ; migration des Claims `EXPOSE` vers des références d'interface.

**Dépendances.** C04, C06.

**Critères d'acceptation.**
- Une version d'interface est immuable ; une rupture exige une nouvelle version majeure.
- Toute opération a un identifiant stable ; tout binding porte mode, provenance, fraîcheur, confiance.
- Un conflit `DECLARED` vs `OBSERVED` est exposé, jamais écrasé silencieusement.
- La détection de rupture est déterministe ; les consommateurs affectés sont listés.
- Un Claim `EXPOSE` legacy pointe vers une interface/opération ou est marqué obsolète.
- Aucune interface publiée sans version, opération et binding.

**Métriques.** Précision/rappel des bindings ; rappel de détection de rupture ; couverture des interfaces ; nombre de conflits ; consommateurs identifiés.

**Risques.** Dérive des spécifications ; parseurs incomplets ; faux positifs de rupture. **Mitigation :** fixtures, diff conservateur, revue humaine, versionnement explicite.

---

### C09 — Mesh dérivé

**Objectif.** Obtenir un graphe d'Applications fiable, reconstruisible et traçable, sans écriture directe.

**Livrables.**
- `mesh/relations` : projection depuis les interfaces, bindings et Claims.
- États : `OBSERVED`, `DECLARED`, `INFERRED`, `CONFIRMED`, `CONTESTED`, `OBSOLETE`.
- Nœuds `ExternalSystem` pour les dépendances hors tenant.
- Recalcul à chaque `binding.changed` ; réconciliation ; API/UI.
- Tests de non-écriture directe et d'isolation tenant.

**Dépendances.** C08.

**Critères d'acceptation.**
- Toute relation possède une dérivation, une provenance et une fraîcheur.
- Aucun endpoint ne permet d'éditer directement une relation ; une confirmation humaine crée une assertion.
- Une relation devient `OBSOLETE` quand sa source change ou disparaît.
- Une relation ne traverse jamais un tenant ; une dépendance externe est un `ExternalSystem`.
- Le Mesh est reconstructible depuis Postgres sans perte.

**Métriques.** Couverture des relations ; relations périmées ; doublons ; consommateurs identifiés ; temps de reconstruction.

**Risques.** Graphe bruyant ; doublons ; surcharge UI. **Mitigation :** états, filtres, confiance, déduplication, pagination.

---

### C10 — Orchestrateur et routage

**Objectif.** Faire router Flore par l'artefact ou par l'identité, sans alias de dépôt, sans conclusion d'absence non prouvée, et avec une identité marquée.

**Livrables.**
- `orchestrateur/routeur` : détection de mention, appel `ApplicationResolver`/`ArtifactRouter`, gestion des ambiguïtés.
- Composeur de réponse : bandeau d'identité, preuves, fraîcheur, actions.
- Contrats d'outils bornés ; prompts corrigés ; tests de non-régression.
- Intégration avec `flore`/`mobilisation` ; feature flag.
- Tests gsf-mockup, absence, ambiguïté, tenant.

**Dépendances.** C03, C06 ; C09 pour la partie multi-applications/Mesh.

**Critères d'acceptation.**
- Une mention de dépôt route vers l'artefact puis le Twin ; elle ne devient jamais un alias d'Application.
- Un nom canonique route vers l'Application ; une ambiguïté liste les candidats.
- Aucune réponse ne dit « n'existe pas » ; le « non observé » est borné et référencé.
- Une réponse provisoire porte le bandeau et les actions ; une promotion reste une demande.
- Chaque affirmation factuelle porte une preuve, un mode et une fraîcheur.
- Les cartes et prompts ne contiennent pas de secret ni d'objet hors tenant.

**Métriques.** Taux de réponse ; taux de réponse provisoire ; validité des citations ; latence p95 ; utilité perçue ; taux d'escalade.

**Risques.** Régression de prompt ; confabulation ; erreur de routage ; latence. **Mitigation :** routage déterministe avant le modèle, jeu d'or, citations, canary, budgets.

---

### C11 — Sécurité multi-tenant, secrets, audit, lecture seule

**Objectif.** Faire du tenant, des secrets, de l'audit et de la lecture seule des propriétés de construction, pas des revues a posteriori.

**Livrables.**
- `securite/tenant` : contexte tenant, RLS, clés composites, filtres obligatoires.
- RBAC/ABAC : rôles, permissions, séparation des devoirs, service accounts.
- Coffre de secrets : `SecretRef`, Vault/KMS, rotation, scopes, audit.
- Audit append-only : événements, hash chain, export SIEM, rétention.
- Politiques connecteurs : lecture seule, egress allowlist, SSRF, taille, quarantaine.
- Redaction : secrets, PII, données classifiées ; tests de fuite.

**Dépendances.** C02, C04.

**Critères d'acceptation.**
- 0 lecture/écriture/recherche/cache/vecteur/prompt inter-tenant ; un ID hors tenant donne `404`.
- 0 secret dans un artefact, prompt, log, erreur, URL ou métrique.
- 100 % des actions sensibles sont auditées ; l'audit est append-only et vérifiable.
- Les connecteurs sont en lecture seule ; aucun scope d'écriture.
- La production refuse le mode démo et `X-Persona` non authentifié.
- Les rôles sont vérifiés côté serveur, jamais côté client.

**Métriques.** Fuites tenant = 0 ; secrets = 0 ; couverture d'audit = 100 % ; âge des secrets ; tests d'isolation au vert ; refus d'écriture.

**Risques.** Requêtes globales historiques ; projections Mongo ; logs ; confused deputy. **Mitigation :** RLS, contexte tenant, tests, revue, redaction, rotation.

---

### C12 — Jeu d'or et évaluation

**Objectif.** Mesurer la qualité réelle, indépendamment du modèle qui produit la réponse, et bloquer les régressions.

**Livrables.**
- `evaluation/jeu_or` : ≥ 280 cas, familles identité, typage, artefacts, interfaces, promotions, sécurité, fraîcheur.
- Harnais reproductible : fixtures gelées, exécution isolée, rapports versionnés.
- Juges calibrés : règles déterministes d'abord, juge LLM seulement pour la sémantique, avec accord humain mesuré.
- Tableaux de bord par tenant et par famille ; gates CI ; seuils d'incident.
- Tests de mutation du résolveur et de la promotion.

**Dépendances.** C03, C06, C07, C10, C11.

**Critères d'acceptation.**
- Chaque cas a entrée, état attendu, réponse attendue, comportements interdits, preuve, propriétaire, version.
- Le jeu est reproductible et versionné ; il ne dépend pas des données de production.
- Les gates bloquent une release si identité, sécurité ou promotion échoue.
- Le juge LLM n'est jamais la seule vérité ; l'accord avec l'humain est mesuré.
- Les tests de mutation détectent une régression du résolveur ou de la promotion.

**Métriques.** Taux de passage par famille ; accord juge/humain ; couverture ; temps d'exécution ; faux confiance.

**Risques.** Sur-apprentissage ; jeu obsolète ; coût ; fausse confiance. **Mitigation :** holdout, rotation, revue humaine, cas adversariaux, seuils par tenant.

---

### C13 — Migration, exploitation et coût

**Objectif.** Basculer sans rupture, exploiter avec des SLO et des budgets, et pouvoir revenir en arrière.

**Livrables.**
- Backfill, double écriture, feature flag `IDENTITY_V2`, canary, rollback.
- Tableaux de bord : latence, erreurs, fraîcheur, coût, backlog, promotions.
- Runbooks : incident identité, fuite tenant, secret compromis, source indisponible, promotion contestée.
- Budgets par tenant, run et réponse ; quotas ; cache ; alertes.
- Sauvegarde/restauration, rétention, legal hold, plan de reprise.

**Dépendances.** C02, C06, C11.

**Critères d'acceptation.**
- Aucune régression des tests existants ; l'UI historique fonctionne pendant la migration.
- Rollback < 15 minutes ; réconciliation des données = 100 %.
- Les SLO sont respectés ; aucun dépassement de budget non expliqué.
- Une restauration est testée ; RTO ≤ 4 h et RPO ≤ 15 min pour l'identité, les preuves et l'audit ; la rétention et le legal hold sont appliqués.
- Les incidents ont un runbook et un post-mortem.

**Métriques.** Couverture de migration ; taux d'erreur ; latence ; coût par consultation/run ; disponibilité ; MTTR.

**Risques.** Perte de données ; indisponibilité ; dépassement de coût ; fatigue des équipes. **Mitigation :** shadow, canary, sauvegardes, budgets, runbooks, rotation.

---

## 4. Phases 0–3 et vertical slice `gsf-mockup`

### 4.1 Vue d'ensemble des phases

| Phase | Durée indicative | Objectif | Critères de sortie | Hors scope |
|---|---|---|---|---|
| **Phase 0 — Socle et vérité** | 3 semaines | Rendre le modèle typé réel : schéma, résolveur, routeur, tenant/audit, jeu d'or v0, feature flag. | Invariants testés ; 0 alias de dépôt ; 0 auto-promotion ; mode ombre ; rollback testé. | Interfaces complètes ; Mesh ; registre externe signé ; échelle. |
| **Phase 1 — Vertical slice `gsf-mockup`** | 6 semaines | Prouver le chemin complet : artefact → Twin provisoire → Application candidate → promotion humaine. | Tous les cas AC-01 à AC-15 ; gates identité/typage/sécurité ; latence ; aucune fuite. | Types de Twin non applicatifs ; auto-promotion ; écriture source. |
| **Phase 2 — Interfaces et Mesh** | 8 semaines | Versionner les contrats, opérations et bindings ; dériver le Mesh ; brancher les twins sans code et le registre externe signé. | Jeu d'or interfaces ; ruptures détectées ; Mesh dérivé ; promotion signée ; 0 écriture directe. | Échelle 10k artefacts ; multi-région. |
| **Phase 3 — Découverte perpétuelle à l'échelle** | 12 semaines | Industrialiser les runs, la fraîcheur, les coûts, la reprise et la sécurité à l'échelle. | 10k artefacts / 1k Applications ; SLO ; budgets ; DR ; pen test ; dépréciation de la double écriture. | Auto-promotion ; remédiation autonome ; graphe inter-tenant. |

**Règle de sortie.** Une phase est terminée par ses critères, pas par sa date. Une phase peut se terminer avec des fonctionnalités reportées explicitement listées ; elle ne peut pas se terminer avec un invariant violé.

### 4.2 Phase 0 — Socle et vérité

**But.** Rendre impossible, au niveau du schéma et du code, de recréer les confusions actuelles.

**Contenu.**
- C01, C02, C03, C11 (socle), C12 (jeu d'or v0).
- Création des tables d'identité, d'artefacts, de résolution, de promotion, d'audit.
- `ApplicationResolver` et `ArtifactRouter` avec tests d'architecture.
- Backfill des Twins existants : chaque `jumeau` devient un `Twin` provisoire ; aucune Application canonique n'est créée automatiquement.
- Projection Mongo enrichie : `identity_kind`, `identity_mark`, `application_id`, `candidate_id`, `tenant_id`, `origin`.
- Feature flag `IDENTITY_V2` en mode `shadow` : les nouveaux chemins calculent, les anciens répondent, les écarts sont comparés sans être exposés.
- Jeu d'or v0 : identité, typage, non-observé, sécurité de base.

**Critères de sortie.**
- Les tests d'architecture interdisent l'alias de dépôt et l'import `identite` → `artefacts`.
- Le backfill est réconcilié : aucun Twin sans artefact, aucun Claim orphelin.
- Le mode ombre montre un écart explicable entre ancien et nouveau routage.
- Le rollback est testé ; le feature flag revient à l'ancien chemin sans perte.
- Aucune Application canonique n'a été créée automatiquement.

### 4.3 Phase 1 — Vertical slice `gsf-mockup`

**But.** Démontrer de bout en bout qu'un dépôt peut produire un Twin provisoire utile, une Application candidate explicite, et une promotion humaine auditée, sans jamais confondre les trois.

**Contenu.**
- C04 (GitHub, manifestes, OpenAPI/config, README), C05, C06, C07, C10 (routage), C11 (tenant/secrets/audit), C12 (jeu d'or v1).
- Un `DiscoveryRun` réel sur `gsf-mockup`.
- Un Twin `nouveau-jumeau` provisoire, lié au dépôt et aux artefacts de contrat/config.
- Une Application candidate avec nom proposé, domaine proposé, propriétaire proposé, preuves.
- Une promotion humaine (ou signée) avec quatre yeux si fusion.
- Une UI minimale : badge provisoire, bandeau de réponse, bouton « demander la promotion », écran de décision.
- Un audit complet : run, findings, résolution, demande, décision, transition.

**Critères de sortie.**
- AC-01 à AC-15 passent.
- Une question « que fait gsf-mockup ? » obtient une réponse provisoire marquée, avec preuves et fraîcheur.
- Une question « gsf-mockup existe-t-elle ? » sans découverte préalable ne dit jamais « non » ; elle dit « non observé » avec périmètre, ou « je n'ai pas encore de résolution ».
- Une promotion ne peut être déclenchée par un dépôt, un mock, un README, un score ou un LLM.
- Un tenant B ne voit ni l'artefact, ni le Twin, ni la candidate, ni l'audit du tenant A.
- Les secrets du connecteur ne figurent ni dans les artefacts, ni dans les prompts, ni dans les logs.
- Le rollback et la désactivation du feature flag sont testés.

### 4.4 Phase 2 — Interfaces et Mesh

**But.** Passer de « je connais des Applications » à « je connais leurs contrats, leurs opérations, leurs implémentations et leurs dépendances prouvées ».

**Contenu.**
- C08, C09, C07 (registre externe signé), C10 (orchestration multi-Twins), C11 (durcissement), C12 (jeu d'or interfaces).
- Interfaces versionnées, opérations, bindings `DECLARED`/`OBSERVED`/`INFERRED`.
- Détection de ruptures et de consommateurs affectés.
- Mesh dérivé, états, fraîcheur, `ExternalSystem`.
- Twins sans code : ServiceNow/CMDB, Datadog, Confluence, schéma de données.
- Promotion par registre externe signé : clé épinglée, issuer allowlist, expiration, nonce.
- Migration des Claims `EXPOSE` vers les interfaces.

**Critères de sortie.**
- Une rupture de contrat est détectée avant publication ; les consommateurs sont listés.
- Un conflit déclaré/observé est visible et non écrasé.
- Le Mesh est reconstructible depuis Postgres ; aucune écriture directe.
- Une promotion signée invalide/rejouée est refusée ; une promotion valide est auditée.
- Les Twins sans code respectent les mêmes règles d'identité et de preuve.
- Le jeu d'or interfaces et Mesh est au vert.

### 4.5 Phase 3 — Découverte perpétuelle à l'échelle

**But.** Faire tourner la découverte en continu, à l'échelle, sans faire exploser le coût ni la confiance.

**Contenu.**
- Webhooks et planification ; découverte incrémentale ; leases, heartbeat, backpressure, DLQ.
- 10 000 artefacts, 1 000 Applications, 100 000 bindings ; tests de charge et de reprise.
- Coût par run et par réponse ; cache ; budgets par tenant ; alertes.
- SLO, DR, restauration, rétention, legal hold.
- Dépréciation de la double écriture legacy ; `jumeau` devient une vue de compatibilité.
- Pen test externe ; exercice d'incident tenant/secret ; revue de sécurité.
- Registre externe à l'échelle ; rotation de clés ; multi-issuer.

**Critères de sortie.**
- Les SLO sont tenus sur 30 jours : disponibilité, latence, fraîcheur.
- Les budgets ne sont pas dépassés sans alerte et justification.
- Une restauration complète est testée ; le RTO/RPO est documenté.
- Un pen test ne trouve aucune vulnérabilité critique ou haute non traitée.
- La double écriture est supprimée sans régression ; les données historiques sont réconciliées.
- Le taux de fausses négations en production est mesuré et expliqué ; aucun cas de promotion automatique.

### 4.6 Vertical slice `gsf-mockup` : séquence détaillée

**Préconditions.**
- Tenant `t1` ; connecteur GitHub configuré en lecture seule ; dépôt `org/gsf-mockup` accessible.
- Le dépôt contient au minimum : un manifeste, un contrat OpenAPI ou un fichier de routes, une configuration d'exposition, un README.
- Aucune entrée CMDB pour `gsf-mockup`.
- `IDENTITY_V2=on` pour le tenant `t1` ; l'ancien chemin reste disponible pour les autres tenants.

| Brique de la vertical slice | Étapes | Cas d'acceptation |
|---|---|---|
| **Source** | 1–2 | AC-01, AC-13 |
| **Contrat / configuration** | 2 | AC-14 |
| **Twin provisoire** | 3–5 | AC-02, AC-03, AC-05 |
| **Promotion** | 9–11 | AC-07, AC-08, AC-09 |

| Étape | Action | Objet créé ou mis à jour | État attendu | Preuve |
|---|---|---|---|---|
| 1 | Le connecteur GitHub découvre `org/gsf-mockup`. | `SourceArtifact` de type `REPOSITORY`, version SHA. | `DISCOVERED` puis `FETCHED`. | Hash, locator, curseur. |
| 2 | Le run vérifie et parse le dépôt. | Artefacts `MANIFEST`, `OPENAPI`/`ROUTES`, `CONFIG`, `README`. | `VERIFIED` puis `PARSED`. | Parser versionné, hash, lignes. |
| 3 | Le run émet un finding de Twin. | `Twin` `nouveau-jumeau`, `PROVISIONAL`. | Lié à au moins un artefact. | `twin_artifact_link`, run id. |
| 4 | Le run émet un finding d'Application candidate. | `Application` `app-…`, `identity_state=CANDIDATE`. | Nom proposé, domaine proposé, preuves. | Finding, assertions. |
| 5 | Le Twin est lié à la candidate. | `Twin.application_id = app-…`. | Toujours `PROVISIONAL`. | Lien, audit. |
| 6 | Une résolution d'artefact est enregistrée. | `ResolutionCase` `RC-ART-…`. | `DECIDED`, issue `RESOLVED_PROVISIONAL`. | Périmètre, artefacts, date. |
| 7 | Une résolution CMDB est enregistrée. | `ResolutionCase` `RC-CMDB-…`. | `NOT_OBSERVED` si CMDB répond ; `INCONCLUSIVE` sinon. | Sources ok/échouées, couverture. |
| 8 | L'utilisateur demande « que fait gsf-mockup ? ». | Réponse de Flore. | `TWIN_PROVISIONAL`, bandeau, preuves, fraîcheur, actions. | `answer.served`, citations. |
| 9 | L'utilisateur clique « demander la promotion ». | `PromotionRequest` `PENDING`. | Aucune transition d'identité. | Idempotence, audit. |
| 10 | Un propriétaire habilité approuve la promotion, puis prononce l'admission (deux décisions tracées). | `PromotionRecord` `APPLIED` ; `Application` `CONFIRMED` ; `Twin` `ACTIVE`. | Deux transitions atomiques, audit. | Audit, événement, réconciliation. |
| 11 | Une nouvelle résolution est demandée. | `ResolutionCase` `RC-APP-…`. | `RESOLVED_CANONICAL`. | Alias, ID externe si présent. |
| 12 | Un tenant B tente d'accéder aux objets de `t1`. | Aucun objet retourné. | `404` ; aucun journal de contenu. | Test d'isolation, audit sécurité. |

**État final attendu.**

| Objet | État |
|---|---|
| `SourceArtifact` repo | `LINKED` (ou `PARSED`) ; version SHA conservée. |
| `SourceArtifact` contrat/config | `PARSED` ; interface/opération dérivées. |
| `Twin` `nouveau-jumeau` | `PROVISIONAL` avant promotion ; `ACTIVE` après. |
| `Application` candidate | `CANDIDATE` avant promotion ; `CONFIRMED` après. |
| `ResolutionCase` artefact | `DECIDED`, `RESOLVED_PROVISIONAL` avant ; `SUPERSEDED` après promotion. |
| `ResolutionCase` CMDB | `DECIDED`, `NOT_OBSERVED` ou `INCONCLUSIVE`. |
| `PromotionRequest` | `PENDING` puis `APPLIED` (ou `REJECTED`) ; l'admission est une décision distincte. |
| `AuditEvent` | Run, résolution, demande, décision, transition. |

**Réponses attendues (formulations).**

- **Provisoire.** « Identité provisoire : Twin `nouveau-jumeau`, lié au dépôt `gsf-mockup` au commit `…`; Application candidate `app-…` non confirmée. Le contrat expose `GET /…` (déclaré) et le code implémente `…` (observé). Preuves : … ; fraîcheur : … ; confiance : … . Pour rendre cette Application canonique, ouvrez une demande de promotion ; un propriétaire habilité décidera. »
- **Canonique.** « Application `…` confirmée le `…` par `…`. Twin actif `nouveau-jumeau`. Sources : … ; fraîcheur : … . »
- **Non observé.** « Non observé dans la CMDB du tenant `t1` au `2026-10-30T…`, périmètre `CI` et `service catalog`. Ce n'est pas une preuve d'absence. Sources interrogées : … ; indisponibles : … ; prochaine vérification : … . »
- **Artefact seul.** « J'ai trouvé un dépôt `gsf-mockup` au commit `…`, mais aucun Twin n'y est encore lié. Je ne peux pas l'appeler une Application. Voulez-vous lancer une découverte ou créer un Twin provisoire ? »

**Interdits dans la démo.**
- Promouvoir automatiquement après l'ingestion, même si le score est élevé.
- Répondre « gsf-mockup est une Application » avant promotion.
- Répondre « cette Application n'existe pas » faute de correspondance.
- Utiliser `gsf-mockup` comme alias d'Application.
- Écrire dans GitHub, même pour corriger un fichier.
- Afficher un objet d'un autre tenant.
- Mettre un secret dans un prompt, un log ou une preuve.

---

## 5. Règles non négociables

| # | Règle | Application concrète | Test / enforcement |
|---|---|---|---|
| **R01** | **Le type précède l'identité.** | Avant de résoudre un nom, on sait s'il désigne une Application, un Twin, un artefact ou une interface. | Test d'architecture sur les types de sujets ; revue de PR. |
| **R02** | **Application est la seule identité métier canonique.** | Aucune autre entité ne peut être promue, aliasée ou affichée comme Application. | Contraintes SQL + tests d'API. |
| **R03** | **Twin n'est pas un processus.** | Un Twin peut exister sans run ; un run peut exister sans Twin. | Tests de cycle de vie séparés. |
| **R04** | **DiscoveryRun/Gardien n'est pas une identité.** | Un run ne peut pas transitionner une Application ; il produit des findings. | Analyse des événements de promotion. |
| **R05** | **SourceArtifact n'est jamais une Application.** | Un dépôt, un fichier, un document ou un ticket reste un artefact. | Test de typage ; revue UI. |
| **R06** | **Aucun nom de dépôt n'est un alias d'Application.** | Le résolveur ne lit pas les artefacts ; le routeur d'artefacts gère les dépôts. | Test d'architecture + test gsf-mockup. |
| **R07** | **Aucune négation sans ResolutionCase.** | Toute réponse négative référence un dossier avec périmètre et date. | Test de réponse ; audit. |
| **R08** | **Absence = « non observé », pas « n'existe pas ».** | La formulation est bornée, avec sources et couverture. | Test de formulation ; revue UX. |
| **R09** | **Source indisponible = inconclusive.** | Un échec de source ne devient jamais une absence. | Test d'issue. |
| **R10** | **Twin provisoire répond avec identité marquée.** | Bandeau, candidat, sources, fraîcheur, actions. | Test de réponse provisoire. |
| **R11** | **Aucune promotion automatique sur un dépôt, un mock, un README, un score ou un LLM.** | Seul un humain habilité ou un registre externe signé peut promouvoir. | Tests de déclencheurs interdits. |
| **R12** | **Promotion humaine ou registre externe signé uniquement.** | Autorité, rôle, preuve, signature, audit. | Tests d'autorisation et de signature. |
| **R13** | **Quatre yeux pour les opérations destructives.** | Fusion, scission, retrait, renommage sensible. | Test de séparation des devoirs. |
| **R14** | **Toute assertion est typée.** | Mode, provenance, fraîcheur, confiance, vérification. | Contrainte de schéma + tests. |
| **R15** | **Les interfaces sont versionnées.** | Contrat, opérations, bindings ; pas de Claim libre comme source de vérité. | Test de publication. |
| **R16** | **Connecteurs déterministes et en lecture seule.** | Aucun LLM dans un connecteur ; aucun scope d'écriture. | Tests de contrat + revue de scope. |
| **R17** | **Pas un agent par connecteur.** | Un connecteur par système, un parser par format, un interpréteur partagé. | Revue d'architecture ; coût par artefact. |
| **R18** | **Le tenant est la frontière supérieure.** | Tout objet, requête, cache, prompt, log, métrique, secret et audit est tenant-scopé. | RLS + tests d'isolation. |
| **R19** | **Secrets = références seulement.** | Vault/KMS ; jamais dans un artefact, prompt, log, URL, erreur, métrique. | Scan + tests de fuite. |
| **R20** | **Audit append-only et infalsifiable.** | Aucune mise à jour/suppression ; hash chain. | Test de tamper + vérification. |
| **R21** | **Mesh dérivé, jamais édité.** | Projection depuis interfaces/bindings/Claims. | Test d'absence d'endpoint d'écriture. |
| **R22** | **Fusion et renommage réversibles.** | `application_id` stable ; scission possible ; tombstone. | Test de rollback. |
| **R23** | **Le LLM propose, ne décide pas.** | `PROPOSED`/`INFERRED` ; aucune transition canonique. | Test de sortie de modèle. |
| **R24** | **Preuve périmée = signalée.** | `valid_until`, `stale`, mention UI. | Test de fraîcheur. |
| **R25** | **Toute modification critique passe le jeu d'or.** | Résolveur, promotion, connecteurs, politique tenant. | Gate CI bloquant. |
| **R26** | **Réel et démo ne se mélangent pas.** | `origin`, badge, filtres, pas de projection silencieuse. | Test de séparation. |

**Conséquence d'une violation.** Une violation de R02, R06, R07, R11, R12, R18, R19 ou R20 est un incident de confiance : elle bloque la release, déclenche un audit et un post-mortem. Les autres violations bloquent la PR ou la phase concernée.

---

## 6. Jeu d'or et métriques

### 6.1 Principes du jeu d'or

1. **Vérité indépendante.** Le jeu d'or est écrit à partir de cas réels et de fixtures gelées, pas généré par le modèle qui répond.
2. **Reproductibilité.** Chaque cas a une version, des fixtures, un résultat attendu et un résultat interdit.
3. **Stratification par tenant et par famille.** Un excellent score global ne compense pas un tenant défaillant.
4. **Cas adversariaux.** Les anti-patterns actuels sont des tests négatifs : alias de dépôt, auto-promotion, fausse négation, Twin comme processus, artefact comme Application.
5. **Juge calibré.** Les règles déterministes d'abord ; le juge LLM seulement pour la sémantique, avec un accord humain mesuré.
6. **Aucun auto-notage.** Le modèle qui produit la réponse ne peut pas être le seul juge de sa qualité.
7. **Holdout.** Une partie du jeu n'est pas visible des développeurs pour détecter le sur-apprentissage.

### 6.2 Composition cible

| Famille | Cas | Ce qu'elle prouve | Exemples |
|---|---:|---|---|
| **Identité et résolution** | 60 | Application vs Twin vs artefact ; alias autoritatif ; ambiguïté ; non-observé ; source en échec. | `gsf-mockup` par dépôt ; Application par nom ; ID CMDB ; deux candidats. |
| **Typage** | 40 | Un artefact n'est jamais une Application ; une interface n'est pas un Claim. | Dépôt, manifeste, OpenAPI, ticket, document, incident. |
| **Artefacts et découverte** | 30 | Idempotence, curseur, quarantaine, reprise, fraîcheur. | Fetch rejoué ; source coupée ; secret dans un fichier ; SHA changé. |
| **Interfaces et bindings** | 50 | Contrats versionnés, opérations, bindings déclarés/observés/inférés, ruptures. | OpenAPI vs route ; champ obligatoire ajouté ; consommateur oublié. |
| **Promotions** | 30 | Autorité, signature, quatre yeux, auto-promotion refusée, réversibilité. | Humain ; registre signé ; signature invalide ; fusion ; scission. |
| **Sécurité** | 40 | Tenant, secrets, injection, SSRF, lecture seule, audit. | IDOR ; secret dans un log ; README piégé ; scope GitHub en écriture. |
| **Fraîcheur et contradictions** | 30 | Preuve périmée, contradiction déclarée/observée, source perdue. | Ancien SHA ; config vs code ; source indisponible. |
| **Total** | **280** | | |

Le jeu peut grandir, mais il ne peut pas rétrécir sans décision d'architecture. Chaque incident de production ajoute un cas.

### 6.3 Format d'un cas

| Champ | Contenu |
|---|---|
| `id` | Identifiant stable, par exemple `ID-RES-014`. |
| `famille` | Identité, typage, artefacts, interfaces, promotions, sécurité, fraîcheur. |
| `tenant` | Tenant de test ; les cas sont stratifiés. |
| `fixtures` | Artefacts, versions, alias, IDs externes, politiques. |
| `input` | Question, référence d'artefact, identifiant, action. |
| `expected_state` | États des objets après l'action. |
| `expected_answer` | Formulation ou champs attendus. |
| `forbidden` | Comportements interdits (promotion, alias, fuite, négation). |
| `evidence` | Preuve attendue (locator, audit, événement). |
| `owner` | Équipe responsable. |
| `version` | Version du cas et date de dernière exécution. |
| `severity` | `P0` (bloquant), `P1` (majeur), `P2` (mineur). |

### 6.4 Métriques

Les cibles sont initiales ; elles seront recalibrées après la baseline de la phase 0. Une cible non atteinte est un signal, pas une excuse.

#### Typage

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Précision de typage | Objets correctement typés / objets typés | ≥ 0,99 | Chaque PR | Jeu d'or |
| Rappel de typage | Objets correctement typés / objets attendus | ≥ 0,95 | Chaque PR | Jeu d'or |
| Artefact classé Application | Nombre de cas où un artefact est promu Application | 0 | Chaque PR | Jeu d'or + incident |
| Interface classée Claim | Nombre d'interfaces réduites à un texte libre | 0 | Chaque PR | Revue + test |

#### Résolution et fausses négations

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Précision top-1 | Résolutions canoniques correctes / résolutions canoniques | ≥ 0,98 | Chaque PR | Jeu d'or |
| Rappel de résolution | Applications résolues / Applications résolubles | ≥ 0,90 | Chaque PR | Jeu d'or |
| Taux d'abstention | `AMBIGUOUS + NOT_OBSERVED + INCONCLUSIVE` / requêtes | 5–15 % | Quotidien | Production |
| Fausses négations | `NOT_OBSERVED` infirmés par une découverte ultérieure / `NOT_OBSERVED` | 0 sur le jeu d'or ; à expliquer en production | Hebdomadaire | Jeu d'or + réconciliation |
| Fusions erronées | Fusions annulées ou corrigées / fusions confirmées | 0 | Mensuel | Audit |
| Latence de résolution p95 | Temps de résolution sans LLM | ≤ 300 ms | Quotidien | Traces |

#### Promotions

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Précision des promotions | Promotions canoniques correctes / promotions | 1,00 | Mensuel | Audit |
| Auto-promotions | Promotions sans décision humaine/signée | 0 | Temps réel | Événements |
| Taux de reversal | Promotions annulées / promotions appliquées | < 1 % | Mensuel | Audit |
| Temps jusqu'à promotion | Médiane entre candidate et décision | À suivre ; cible < 10 jours ouvrés | Hebdomadaire | Audit |
| Demandes en attente > 30 jours | Backlog de promotion | < 10 % des candidats | Hebdomadaire | File |

#### Consultations

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Taux de réponse | Questions avec réponse non vide / questions | ≥ 95 % | Quotidien | Production |
| Taux de réponse provisoire | Réponses `TWIN_PROVISIONAL` / réponses Twin | À suivre ; doit décroître avec la maturité | Hebdomadaire | Production |
| Validité des citations | Citations vérifiées / citations | ≥ 0,99 | Chaque PR + quotidien | Contradicteur |
| Affirmations appuyées | Affirmations avec preuve / affirmations factuelles | ≥ 0,95 | Chaque PR | Jeu d'or |
| Utilité perçue | Note utilisateur (1–5) | ≥ 4,0 | Hebdomadaire | Feedback |
| Taux d'escalade | Réponses nécessitant une action humaine / réponses | À suivre | Hebdomadaire | Production |
| Latence de réponse p95 | Premier texte + réponse complète | ≤ 8 s | Quotidien | Traces |

#### Fraîcheur

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Âge p95 des preuves | Âge de la preuve au moment de la réponse | ≤ 24 h pour le code ; ≤ 7 j pour la doc | Quotidien | Traces |
| Réponses périmées | Réponses avec preuve au-delà de `valid_until` / réponses | ≤ 1 % | Quotidien | Production |
| Latence de détection de changement p95 | Commit/page → détection | ≤ 5 min avec webhook ; ≤ 1 h en polling | Quotidien | Runs |
| Couverture des sources | Applications avec au moins une source fraîche / Applications | ≥ 90 % | Hebdomadaire | Registre |
| Backlog de runs en échec | Runs `FAILED`/`ORPHANED` non repris | 0 après 24 h | Quotidien | Runs |

#### Latence, disponibilité, coût

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Disponibilité API | Requêtes réussies / requêtes | 99,9 % | Mensuel | SLO |
| Latence de run p95 | Run de 1 000 artefacts | ≤ 10 min | Hebdomadaire | Runs |
| Coût par consultation | Tokens + outils + infrastructure | ≤ 0,05 $US médian (à recalibrer) | Quotidien | Facturation |
| Coût par run | Coût d'un run de 1 000 artefacts | ≤ 2 $US (à recalibrer) | Hebdomadaire | Facturation |
| Appels LLM par artefact | Appels modèle / artefact traité | ≤ 1 | Hebdomadaire | Traces |
| Cache hit | Réponses/preuves servies par cache / total | ≥ 60 % | Quotidien | Traces |
| Dépassement de budget | Budgets dépassés sans alerte | 0 | Temps réel | Budgets |

#### Secrets et fuites tenant

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Fuites de secrets | Secrets détectés dans artefacts/prompts/logs/erreurs/metrics | 0 | Temps réel | Scan + audit |
| Couverture du scan | Artefacts scannés / artefacts ingérés | 100 % | Quotidien | Scan |
| Âge maximal d'un secret | Rotation | ≤ 90 jours | Mensuel | Coffre |
| Fuites tenant | Accès inter-tenant détecté | 0 | Temps réel | Tests + audit |
| Tests d'isolation | Tests d'isolation au vert | 100 % | Chaque PR | CI |
| Couverture d'audit | Actions sensibles auditées / actions sensibles | 100 % | Mensuel | Audit |
| Refus d'écriture source | Tentatives d'écriture connecteur refusées | 100 % | Chaque PR | Tests |

#### Interfaces et Mesh

| Métrique | Définition | Cible initiale | Fréquence | Source |
|---|---|---:|---|---|
| Précision des bindings | Bindings corrects / bindings vérifiés | ≥ 0,95 | Chaque PR | Jeu d'or |
| Rappel des bindings | Bindings trouvés / bindings attendus | ≥ 0,90 | Chaque PR | Jeu d'or |
| Rappel de rupture | Ruptures détectées / ruptures attendues | ≥ 0,90 | Chaque PR | Jeu d'or |
| Couverture des interfaces | Interfaces avec version + binding / interfaces exposées | ≥ 80 % | Mensuel | Registre |
| Relations périmées | Relations `OBSOLETE` non recalculées | 0 après 24 h | Quotidien | Mesh |
| Doublons de relations | Arêtes dupliquées / arêtes | < 2 % | Hebdomadaire | Mesh |

### 6.5 Gates de release

| Gate | Condition | Blocage |
|---|---|---|
| **G0 — Socle** | Invariants testés ; 0 alias de dépôt ; 0 auto-promotion ; migration réversible ; RLS de base. | Aucune release. |
| **G1 — Vertical slice** | AC-01 à AC-15 ; identité/typage/sécurité au vert ; 0 fuite tenant ; 0 secret ; p95 résolution ≤ 300 ms ; p95 réponse ≤ 8 s. | Release de la phase 1. |
| **G2 — Interfaces/Mesh** | Jeu d'or interfaces au vert ; rappel de rupture ≥ 0,90 ; Mesh dérivé ; promotion signée ; 0 écriture directe. | Release de la phase 2. |
| **G3 — Échelle** | 10k artefacts / 1k Applications ; SLO 30 jours ; budgets ; DR ; pen test ; 0 fausse négation non expliquée. | Release de la phase 3. |

### 6.6 Pièges de mesure

- **La moyenne cache les faux négatifs.** Toujours publier par famille et par tenant.
- **Le juge LLM n'est pas la vérité.** Il mesure la sémantique, pas l'identité ; l'accord humain doit être mesuré.
- **Un `NOT_OBSERVED` n'est pas un faux.** Il ne devient un faux négatif que si une découverte ultérieure prouve l'existence.
- **Le nombre de promotions n'est pas un objectif.** Une promotion correcte vaut mieux que dix promotions rapides.
- **Les noms de dépôts ne sont pas des alias dans le jeu d'or.** Un cas qui encode l'anti-pattern doit être supprimé.
- **Les données de démonstration ne comptent pas.** Les scores sont calculés sur des fixtures réelles ou explicitement étiquetées.
- **Le coût par réponse doit inclure les outils.** Un modèle moins cher avec plus d'appels peut coûter plus cher.

### 6.7 Seuils d'incident

| Sévérité | Déclencheur | Action |
|---|---|---|
| **SEV1** | Auto-promotion ; fuite tenant ; fuite de secret ; fusion canonique erronée ; audit falsifié. | Gel des releases, incident sécurité, post-mortem, correction avant reprise. |
| **SEV2** | Fausse négation en production ; réponse périmée > 1 % ; promotion annulée ; gate du jeu d'or rouge. | Revue d'incident, correctif sous 5 jours, cas ajouté au jeu d'or. |
| **SEV3** | Dépassement de budget > 20 % ; doublons > 10 % ; backlog de résolution > 30 jours. | Plan d'action, suivi hebdomadaire. |

---

## 7. Différé et pourquoi

| Élément différé | Pourquoi maintenant, non | Signal de réexamen | Phase cible |
|---|---|---|---|
| **Types de Twin non applicatifs** (processus, capacité, parcours, organisation) | Le modèle d'identité applicative doit d'abord être prouvé. Chaque type ajoute ses propres règles de résolution et de preuve. | Un cas d'usage métier validé ne pouvant pas être représenté par une Application. | Après phase 3 |
| **Auto-promotion ou auto-fusion par ML** | Une fusion erronée est difficile à défaire et coûteuse en confiance. Le LLM n'a pas l'autorité. | Un registre signé couvre la majorité des cas et le taux d'erreur humain est mesuré. | Jamais pour l'identité ; éventuellement pour des suggestions. |
| **Un agent par connecteur** | Non déterministe, coûteux, difficile à tester, surface d'attaque. Un connecteur doit être un adaptateur, pas un raisonneur. | Aucun : l'interprétation reste un service partagé. | Jamais |
| **Découverte runtime comme autorité** (eBPF, APM, traces) | Bruit, données personnelles, couverture partielle. Utile comme preuve `OBSERVED`, pas comme identité. | Couverture > 80 % et politique de données validée. | Phase 3+ |
| **Écriture bidirectionnelle vers la CMDB** | Le principe est la lecture seule ; une écriture erronée dans la CMDB est un incident majeur. | Un workflow signé, réversible et audité est exigé par le propriétaire de la CMDB. | Après phase 3 |
| **Graphe global inter-tenant** | La frontière tenant est une exigence de sécurité et de conformité. Un client ne doit pas voir l'empreinte d'un autre. | Un produit multi-tenant explicitement partagé, avec consentement et chiffrement. | Hors périmètre |
| **Neptune / OpenSearch** | Postgres suffit pour les volumes actuels ; ajouter deux infrastructures augmente le coût et les modes de panne. | > 10 000 Applications ou > 1 000 000 d'arêtes, ou requêtes de graphe p95 > 2 s. | Phase 3+ |
| **Recherche vectorielle comme décision d'identité** | Les embeddings produisent des faux positifs non explicables. Ils peuvent générer des candidats, jamais une décision. | Un taux de faux positifs mesuré et un workflow humain robuste. | Phase 3+ |
| **Multi-région actif-actif** | Complexité de cohérence, de clés et d'audit ; le RTO/RPO n'est pas encore validé. | Exigence de continuité > 99,99 % ou présence réglementaire. | Après phase 3 |
| **Remédiation autonome** (modifier un dépôt, un ticket, une configuration) | Le produit doit d'abord être fiable en lecture ; l'écriture automatisée augmente le risque. | Un cadre d'approbation et de rollback éprouvé. | Hors périmètre |
| **Fine-tuning d'un modèle d'identité** | Pas assez de données étiquetées ; le jeu d'or et les règles déterministes sont plus rentables. | Volume de cas > 10 000 et erreur résiduelle mesurée. | Phase 3+ |
| **Diff sémantique des interfaces par LLM** | Le diff déterministe suffit pour les ruptures ; le LLM peut expliquer, pas décider. | Formats non structurés majoritaires. | Phase 3+ |
| **Streaming temps réel de toutes les sources** | Coût et complexité ; les webhooks des sources critiques suffisent. | Besoin de fraîcheur < 1 min sur une source non webhookée. | Phase 3+ |
| **Data lake / entrepôt analytique** | Le produit n'a pas besoin d'un lake pour répondre ; les données opérationnelles suffisent. | Besoin d'analyse historique à grande échelle. | Hors périmètre |
| **UI d'analytique portefeuille complète** | Une UI avancée sur des identités instables propage l'erreur. | Taux de résolution > 95 % et backlog de promotion maîtrisé. | Phase 2+ |
| **Policy engine externe (Cedar/Verified Permissions)** | RLS + RBAC applicatif suffisent pour un tenant pilote ; l'externalisation ajoute un couplage. | Plusieurs tenants, politiques complexes, exigence d'audit centralisé. | Phase 3+ |
| **Routage transfrontalier de modèles pour données restreintes** | Dépend des exigences légales et des contrats. Par défaut, on ne route pas. | Avis juridique et politique de classification validés. | Selon tenant |
| **Write-back vers les systèmes sources** | Lecture seule par principe ; un connecteur ne doit pas pouvoir modifier la source. | Un besoin métier explicite, un scope d'écriture dédié et un audit renforcé. | Hors périmètre |

**Ce qui n'est pas différé.** Le tenant, les secrets, l'audit, la lecture seule, la non-promotion automatique, le non-observé et la séparation Twin/Application ne sont pas des options de phase. Ils sont dans le socle.

---

## 8. Première tranche exécutable

### 8.1 Objectif et périmètre

**Tranche T0 — « Identité typée en ombre, `gsf-mockup` de bout en bout, promotion humaine. »**

Durée indicative : 4 à 6 semaines, 4 personnes (1 identité/backend, 1 connecteurs/parsers, 1 frontend/UX, 1 sécurité/évaluation). Livrable : un chemin complet, testé, derrière un feature flag, sans auto-promotion. La séquence ci-dessous est une cible ; elle s'étire si le backfill ou les tests de sécurité l'exigent.

**Dans le périmètre.**
- Schéma `002_identite.sql` et backfill.
- `ApplicationResolver` + `ArtifactRouter` + `ResolutionCase`.
- Connecteur GitHub minimal + parseurs manifeste/OpenAPI/config/README.
- `DiscoveryRun` réel et `Gardien` minimal (déclenchement manuel + polling).
- Twin provisoire, Application candidate, bandeau d'identité.
- `PromotionRequest` + décision humaine + audit.
- Isolation tenant de base, secrets par référence, lecture seule.
- Jeu d'or v1 (identité, typage, sécurité, gsf-mockup).
- Feature flag `IDENTITY_V2=off|shadow|on`, rollback.

**Hors périmètre.**
- Interfaces complètes, Mesh complet, twins sans code, registre externe signé (stub de vérificateur seulement).
- Échelle 10k artefacts, multi-région, écriture source, auto-promotion.

### 8.2 Modules pressentis

Deux fondations existent déjà dans l'arbre de travail et doivent être réutilisées, pas dupliquées :
- `backend/jumeau/identite.py` fournit déjà un chemin typé `source → twin → application candidate`, une règle de provisoire et un résultat « absence non prouvée ». T0 la transforme en service `ApplicationResolver`/`ArtifactRouter` avec `ResolutionCase` persistant et identifiant de candidate distinct du Twin.
- `backend/jumeau/interfaces.py` fournit déjà des parseurs OpenAPI/configuration, des assertions `declared`, des identifiants stables et la redaction des secrets d'URL. T0 l'utilise comme base du module `interfaces`, en ajoutant la persistance, le versionnement et les bindings.
- Le vocabulaire existant `Contract`/`declared` est mappé vers `Interface` (ou `InterfaceVersion`)/`DECLARED` ; l'API accepte les deux formes en lecture pendant la migration, la forme cible est la seule écrite.

| Module | Responsabilité | Dépend de | Tests |
|---|---|---|---|
| `backend/jumeau/identite.py` (existant) | Fondation de résolution typée. | Registre actuel. | Tests existants + nouveaux cas. |
| `backend/jumeau/interfaces.py` (existant) | Fondation de parseurs de contrats/config. | Artefacts. | Tests existants + nouveaux cas. |
| `backend/identite/domain` | Types, états, invariants, transitions. | — | Unitaires, propriétés. |
| `backend/identite/depot` | Persistance `Application`, alias, IDs externes, Twin, promotion. | `002_identite.sql` | Intégration Postgres. |
| `backend/identite/resolveur` | Résolution applicative déterministe. | `domain`, `depot` | Unitaires + jeu d'or identité. |
| `backend/identite/promotion` | Demande, décision, autorité, audit, rollback. | `domain`, `depot` | Unitaires + sécurité. |
| `backend/identite/routes` | API identité/promotion. | `resolveur`, `promotion` | Contrat + auth. |
| `backend/artefacts/registre` | `SourceArtifact`, versions, hash, quarantaine. | `002_identite.sql` | Intégration. |
| `backend/artefacts/routeur` | Référence d'artefact → Twin/Application. | `registre` | Unitaires + gsf-mockup. |
| `backend/artefacts/connecteurs/github` | Découverte/fetch GitHub en lecture seule. | `registre` | Contrat avec fixtures. |
| `backend/artefacts/parseurs/*` | Manifeste, OpenAPI, routes, config, README. | `registre` | Fixtures + snapshots. |
| `backend/decouverte/runs` | `DiscoveryRun`, findings, coûts, reprise. | `artefacts`, `identite` | Intégration + idempotence. |
| `backend/decouverte/gardien` | Planification et exécution. | `runs` | Tests de bail/panne. |
| `backend/interfaces/contrats` | `Interface`, `Operation`, `Binding` minimaux pour OpenAPI. | `artefacts` | Unitaires. |
| `backend/mesh/projection` | Projection minimale des relations à partir des bindings. | `interfaces` | Unitaires. |
| `backend/securite/tenant` | Contexte tenant, RLS, filtres. | `002_identite.sql` | Tests d'isolation. |
| `backend/securite/secrets` | `SecretRef`, coffre, redaction. | `tenant` | Tests de fuite. |
| `backend/securite/audit` | Événements append-only, hash chain. | `tenant` | Tests de tamper. |
| `backend/evaluation/jeu_or` | Cas, harnais, rapports. | Tous | CI. |
| `backend/jumeau/*` | Adaptateurs de compatibilité. | Nouveaux modules | Non-régression. |

### 8.3 Contrats T0

| Contrat | Producteur | Consommateur | Invariant |
|---|---|---|---|
| `ResolutionQuery` → `ResolutionResult` | API identité | Orchestrateur, UI | Toujours un `case_id` ; jamais une décision implicite. |
| `ArtifactRef` → `ArtifactRoute` | API artefacts | Orchestrateur, découverte | Toujours un `SourceArtifact` ; jamais un alias d'Application. |
| `TwinView` | API Twin | UI, orchestration | Contient `identity_mark`, `application_id`, `sources`, `freshness`. |
| `PromotionRequest` | API promotion | UI, audit | `PENDING` ne change pas l'identité ; `APPLIED` est atomique. |
| `DiscoveryRunView` | API découverte | UI, exploitation | État, curseur, coût, erreurs, findings. |
| `AuditEvent` | Sécurité | Audit, SIEM | Append-only, tenant, acteur, action, objet, hash. |
| `Error` | API | Tous | `404` hors tenant ; `409` conflit d'état ; `422` invariant ; jamais de secret. |

### 8.4 Migration T0

1. **Créer** `002_identite.sql` sans supprimer les tables historiques.
2. **Backfill** : chaque `jumeau` devient un `Twin` `PROVISIONAL` avec `legacy_jumeau_id` ; ses `source` GIT deviennent des `SourceArtifact` ; les Claims restent attachés au Twin.
3. **Aucune Application canonique automatique** : les `jumeau` existants produisent des candidats si une identité externe existe, sinon des Twins provisoires sans candidate.
4. **Double écriture** : les chemins historiques écrivent encore `jumeau`/`source` ; les nouveaux chemins écrivent les nouvelles tables et projettent l'ancien format.
5. **Projection Mongo** : ajouter `identity_kind`, `identity_mark`, `application_id`, `candidate_id`, `tenant_id`, `origin`. Les documents de démonstration restent `origin=DEMO`.
6. **Feature flag** : `IDENTITY_V2=off` (ancien), `shadow` (calcul et comparaison), `on` (nouveau chemin exposé). Le retour à `off` ne perd aucune donnée.
7. **Réconciliation** : compter les Twins, artefacts, Claims, candidats ; comparer avant/après ; aucun orphelin.

### 8.5 Tests et définition de terminé

**Tests obligatoires.**
- Unitaires : resolveur, routeur, états, promotion, autorité.
- Architecture : pas d'import `identite` → `artefacts` ; pas d'alias de dépôt.
- Contrat : connecteur GitHub, parseurs, API.
- Intégration : gsf-mockup de bout en bout ; run rejoué ; source coupée ; SHA changé.
- Sécurité : IDOR tenant, secrets, prompt injection, lecture seule, audit.
- Jeu d'or : identité, typage, promotions, sécurité.
- Non-régression : suite `backend/jumeau/tests` existante.

**Définition de terminé.**
- AC-01 à AC-15 passent.
- 0 alias de dépôt dans le résolveur.
- 0 auto-promotion.
- 0 fuite tenant dans les tests.
- 0 secret dans les artefacts/prompts/logs.
- Toute réponse provisoire porte le bandeau et les actions.
- Toute réponse négative référence une `ResolutionCase`.
- La promotion est auditée et réversible.
- Le rollback est testé.
- Le jeu d'or v1 est publié avec ses résultats.

### 8.6 Séquence de travail

| Semaine | Identité | Artefacts/découverte | UI/UX | Sécurité/évaluation |
|---|---|---|---|---|
| **S1** | C01, C02 : types, schéma, contraintes. | Contrat de connecteur, fixtures GitHub. | Maquette badge/bandeau/promotion. | Menaces, tests d'isolation, jeu d'or v0. |
| **S2** | C03 : resolveur, routeur, `ResolutionCase`. | C04 : GitHub, parseurs manifeste/OpenAPI/config. | Écran de résolution et d'ambiguïté. | RLS, secrets, audit. |
| **S3** | C06 : Twin provisoire, candidate. | C05 : run, findings, reprise. | Bandeau provisoire, actions. | Tests gsf-mockup, secrets, injection. |
| **S4** | C07 : promotion, décision, audit. | Réconciliation, performance. | Écran de promotion, audit. | Jeu d'or v1, gates, rollback. |

### 8.7 Démonstration d'acceptation

1. Importer `org/gsf-mockup` dans le tenant `t1`.
2. Montrer le `DiscoveryRun`, les artefacts, le Twin `nouveau-jumeau`, la candidate.
3. Demander « que fait gsf-mockup ? » : réponse provisoire marquée, preuves, fraîcheur, actions.
4. Demander « gsf-mockup existe-t-elle ? » : `NOT_OBSERVED` borné ou `INCONCLUSIVE`, jamais « non ».
5. Ouvrir une demande de promotion ; montrer qu'elle est `PENDING` et que l'identité n'a pas changé.
6. Approuver avec un propriétaire habilité, puis prononcer l'admission ; montrer `PromotionRecord`, `Application CONFIRMED`, `Twin ACTIVE`, audit.
7. Redemander « que fait gsf-mockup ? » : réponse canonique, avec alias métier (pas le dépôt) et preuves.
8. Tenter une promotion automatique par un run ou un LLM : refus, aucun événement.
9. Tenter un accès depuis le tenant `t2` : `404`, aucune fuite.
10. Montrer le rollback : `IDENTITY_V2=off`, l'ancien chemin fonctionne, aucune perte.

---

## 9. Références

### Documents
- [ADR-0001 — Identité typée : Application, Twin et découverte perpétuelle](../adr/0001-identite-typed-twin-discovery.md)
- `docs/MERIDIAN_Architecture_Jumeau_v1.md`
- `docs/MERIDIAN_Jumeau_Sources_v1.md`
- `docs/MERIDIAN_Jumeau_Mobilisation_v1.md`
- `docs/MERIDIAN_Jumeau_Harness_Agentique_v3.md`
- `docs/MERIDIAN_Domain_Model_Information_Architecture_v1.md`
- `docs/MERIDIAN_Security_Governance_Trust_Model_v1.md`
- `docs/MERIDIAN_Discovery_Maturation_Engine_v1.md`
- `docs/MERIDIAN_Technical_Architecture_v1.md`

### Code de référence (état actuel, à faire évoluer)
- `backend/jumeau/depot.py` — preuves, Claims, jumeaux.
- `backend/jumeau/registre.py` — projection du registre.
- `backend/jumeau/carte.py` — carte d'un Twin.
- `backend/jumeau/mobilisation.py` — mobilisation multi-Twins.
- `backend/jumeau/flore.py` — réponse et routage actuels.
- `backend/jumeau/naissance.py` — naissance d'un Twin.
- `backend/jumeau/gardien.py` — passe de découverte actuelle.
- `backend/jumeau/schema.sql` — schéma historique.
- `backend/jumeau/schemas.py` — états de vérification.
- `backend/server.py` — API et orchestration.

### Principe final

> **Un dépôt n'est pas une application. Un Twin n'est pas une application. Un run n'est pas un Twin. Une absence n'est pas une preuve. Une promotion n'est pas un effet de bord.**

Ce programme ne vaut que si ces cinq phrases sont vraies dans le schéma, dans les API, dans les prompts, dans les tests et dans l'écran.
