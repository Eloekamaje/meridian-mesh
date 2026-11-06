# ADR-0033 — Liens entre composants : producteurs, consommateurs et soupçons

- **Statut :** proposed
- **Date :** 2026-11-06
- **Décideurs :** Produit, architecture, propriétaires de domaine, sécurité
- **Portée :** découverte des producteurs et consommateurs, appariement des interfaces, revue humaine
- **Décisions liées :** ADR-0001, ADR-0003, ADR-0004, ADR-0010, ADR-0031, ADR-0032
- **Formalisation détaillée :** [Découverte des liens entre composants — boucle d'enquête, agentique et naissance](../architecture/decouverte-liens-agentique.md)
- **Prérequis :** aucun accès serveur, aucun secret, aucun export WebSphere obligatoire

---

## 1. Contexte

Une API exposée n'identifie pas son application. On voit souvent :

```text
GET /accounts/{id}
  → route de passerelle
  → service comptes-api
  → application ?
```

Le nom du service n'est pas le propriétaire. La passerelle n'est pas le producteur. Le dépôt
n'est pas l'application. Il faut donc séparer :

| Objet | Question |
|---|---|
| `Composant` | frontend, backend, worker, batch, gateway, ESB |
| `Interface` | quelle route, opération SOAP, file ou topic est exposé |
| `Appel` | quelle URL, propriété, file ou service est appelé |
| `Deploiement` | quel service, hôte et route de passerelle portent le composant |
| `LienPropose` | quel composant consomme quelle interface, avec quelles preuves |
| `QuestionLien` | ce qui manque pour conclure |

Le serveur d'application peut être inaccessible. La découverte doit donc fonctionner à partir
de ce qui est **publié** : code, configuration, Helm, manifests de déploiement, contrats,
gateway et traces. L'humain complète ensuite ce qui manque.

---

## 2. Décision

Méridian ajoute un **moteur de liens entre composants**, indépendant de tout serveur :

```text
Sources publiées
  → extraction déterministe (code, config, Helm, déploiement, contrats)
      → résolution d'identité (service, hôte, route, file)
          → appariement des opérations
              → liens proposés + questions ouvertes
                  → revue humaine
                      → lien confirmé, rejeté ou contesté
```

### 2.1 Ce que le moteur extrait

| Source | Producteurs | Consommateurs |
|---|---|---|
| Java | routes Spring, `@JmsListener`, contrats | Feign, RestTemplate, WebClient, JMS, Kafka |
| JavaScript/TypeScript | — | axios, fetch |
| OpenAPI / WSDL / GraphQL / gRPC / AsyncAPI | opérations exposées | — |
| Configuration | nom de service, contexte | URL, propriété, endpoint |
| Kubernetes | Deployment, Service, Ingress | variables d'environnement |
| Helm | image, service, ingress | variables d'environnement |
| Traces | — | appels observés |

Aucun fichier de secret n'est requis. Une URL avec identifiants ou un secret de requête est
ignorée, et la clé `password`/`token`/`secret` n'entre jamais dans le modèle.

### 2.2 Résolution d'identité

L'index résout, dans cet ordre :

```text
propriété ${accounts.base-url}
  → configuration de l'environnement
  → URL
  → hôte ou nom de service
  → route de passerelle la plus spécifique
  → service Kubernetes
  → composant
  → application
```

Un hôte d'ingress n'est **jamais** rattaché au composant gateway comme producteur : c'est une
porte d'entrée. La route désigne un service, et c'est ce service qui désigne le producteur.

### 2.3 Appariement des opérations

Pour HTTP, le moteur compare les suffixes de chemins, pas les chaînes complètes :

```text
consommateur : /accounts/123
producteur   : /api/accounts/{id}
suffixe      : /accounts/{id}
```

Cela absorbe un préfixe de passerelle ou un contexte applicatif sans confondre `/accounts`
avec `/{id}`. Un appariement doit contenir au moins un segment littéral commun ; sinon il est
trop vague et devient une question.

Pour JMS/Kafka, la file ou le topic doit correspondre exactement. Pour SOAP, l'action est
comparée quand elle est connue ; sinon le service identifié suffit à proposer l'interface.

### 2.4 Trois niveaux de preuve

Un lien porte trois vérifications distinctes :

| Vérification | Signification |
|---|---|
| `implemente` | le producteur expose l'opération dans son code ou son contrat |
| `configure` | le consommateur est configuré pour joindre ce service/hôte |
| `observe` | une trace confirme l'appel en runtime |

Un lien `implemente + configure` est un **soupçon fort**. Il n'est jamais confirmé
automatiquement : l'état reste `suggere` jusqu'à la revue humaine.

### 2.5 Nature du lien

| Nature | Condition | Usage |
|---|---|---|
| `interne` | même `application_id` | lien entre composants d'une application ; pas une relation de Mesh |
| `mesh` | applications distinctes | candidat à `PropositionRelation` |
| `externe` | hôte public non rattaché | dépendance tierce, pas un Twin interne |

Un lien `mesh` n'est éligible à une relation que si sa portée est `SERVICE`, `PARTNER` ou
`PUBLIC`. Une portée `UNKNOWN` reste visible, avec la question de frontière.

### 2.6 Contradiction

Deux producteurs incompatibles pour la même opération et le même consommateur ne sont jamais
fusionnés. Les deux liens passent à `conteste`, avec une `QuestionLien` de type
`CONTRADICTION` et les candidats. Le propriétaire tranche.

### 2.7 Revue humaine

`revoir_lien(lien, decision, acteur, motif)` accepte, rejette ou conteste. La preuve de revue
est datée, attribuée et conservée. Une déclaration d'identité (`IdentiteDeclaree`) peut
compléter un service manquant ; le moteur est ensuite rejoué.

Un lien Mesh éligible devient une `PropositionRelation` via `vers_proposition` ; une question
ouverte devient un `ResolutionCase` via `vers_resolution_case`. La conversion ne confirme
rien : elle transporte les preuves, la portée, les inconnues et la prochaine vérification.

---

## 3. Implémentation

| Fichier | Rôle |
|---|---|
| `backend/meridian/domain/liens_composants.py` | modèle : composant, interface, appel, déploiement, lien, question |
| `backend/meridian/adapters/outbound/connectors/decouverte_composants.py` | extraction Java/JS, contrats, configuration, Kubernetes, Helm, traces |
| `backend/meridian/application/moteur_liens.py` | index d'identités, appariement, contradictions, revue, conversion en proposition ou en cas, pont depuis les manifestes, filtre local |
| `backend/meridian/adapters/outbound/postgres/decouverte_naissance.py` | handler `twin.born` : découverte locale bornée, propositions et cas |
| `backend/meridian/adapters/outbound/connectors/java_source.py` | `extraire(fichier, texte)` réutilisable sans disque |
| `scripts/decouvrir-liens-composants.py` | CLI multi-dépôts, JSON, sans base |
| `backend/meridian/tests/test_moteur_liens.py` | jeu d'or de quatorze cas |
| `backend/meridian/tests/test_decouverte_naissance.py` | quatre cas de découverte locale à la naissance |

Le CLI s'utilise sans base ni serveur :

```bash
python scripts/decouvrir-liens-composants.py \
  --depot comptes:comptes-api:/chemin/comptes \
  --depot antifraude:antifraude-backend:/chemin/antifraude \
  --environnement prod
```

Le même moteur peut repartir des manifestes et bindings déjà persistés :
`extractions_depuis_manifests(manifests, bindings)` transforme les expositions,
consommations, routes, services et propriétés en entrées du moteur, sans relire les dépôts.

Le handler `twin.born` exécute d'abord le résolveur historique, puis cette découverte locale
bornée. `filtrer_local` ne garde que les liens et questions où le Twin naissant est impliqué.
Les propositions éligibles et les cas de frontière ou de question sont persistés ; aucun agent
n'est appelé et aucun lien n'est confirmé.

---

## 4. Jeu d'or

Le fixture vérifie :

1. lien inter-app REST Antifraude → Comptes, avec preuves code, config, contrat, ingress ;
2. frontend → backend de la même application classé `interne` ;
3. gateway seule : service `comptes-api` identifié, producteur inconnu → question ;
4. API tierce Stripe classée `externe`, jamais Twin interne ;
5. configuration et trace contradictoires → deux liens `conteste` et une question ;
6. revue humaine qui confirme le soupçon ;
7. déclaration humaine qui complète l'identité d'un service ;
8. secret de configuration jamais repris ;
9. Helm `values.yaml` suffit à identifier le producteur ;
10. JMS : émetteur → listener sur la même file ;
11. WSDL + configuration WSDL : lien SOAP ;
12. conversion d'un lien en `PropositionRelation` et d'une question en `ResolutionCase` ;
13. pont depuis les manifestes et bindings existants ;
14. découverte locale `twin.born`, idempotente et bornée au Twin naissant.

---

## 5. Limites assumées

- Le moteur travaille sur des fichiers déjà collectés ; le branchement à l'ingestion GitHub,
  Nexus ou artefacts reste à faire.
- Les routes JAX-RS, les annotations SOAP Java et les bindings JNDI ne sont pas encore
  extraits ; WSDL et configuration WSDL couvrent le premier cas SOAP.
- La portée d'une file JMS n'est pas déduite d'un ingress HTTP : elle reste `UNKNOWN` jusqu'à
  une déclaration de frontière.
- Le matching de templates reste volontairement conservateur ; un cas ambigu devient une
  question, jamais une attribution au hasard.
- La persistance des `LienPropose` et leur affichage dans le volet du Twin restent à brancher.
- Aucun export WebSphere n'est requis ni supposé.

---

## 6. Critères d'acceptation

- un lien inter-app n'est produit que si un producteur et un consommateur sont identifiés ;
- un lien de même application est `interne` et n'entre pas dans le Mesh ;
- une gateway seule ne produit pas d'attribution abusive ;
- une API tierce n'est pas un Twin interne ;
- une contradiction n'est jamais écrasée ;
- un lien sans preuve suffisante reste `suggere` avec une question exacte ;
- un secret n'apparaît jamais dans le rapport ;
- le jeu d'or passe sans base, sans réseau et sans serveur d'application.
