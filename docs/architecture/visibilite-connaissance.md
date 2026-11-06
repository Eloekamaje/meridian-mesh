# Visibilité de la connaissance

**Date :** 2026-11-05
**Statut :** décision retenue : `claim_share` + `authorize` (section 12). Le modèle à quatre axes (sections 3 à 11) est conservé comme alternative étudiée.
**Objet :** permettre à un Twin d’encapsuler certaines connaissances et de publier une partie contrôlée dans la maille.

> **Décision retenue (2026-11-05) :** le partage est **publication-centric**. Le Claim reste privé par défaut ; `claim_share` est le seul acte de partage ; `authorize` est la seule règle de projection. La fiche est un rendu des sept questions, pas le modèle.

---

## 1. Problème

Aujourd’hui :

- `tenant_id` isole les tenants ;
- RLS est opt-in (`JUMEAU_RLS=1`) ;
- `document_chunk.acl` et `graph_community.acl` filtrent les chunks et les communautés ;
- `claim`, `preuve`, `fiche_vivante` et `source.exploration` n’ont **aucune enveloppe de visibilité**.

Conséquence : une connaissance est soit privée au tenant entier, soit visible par tous ceux qui peuvent lire le twin. On ne peut pas dire :

> « Cette connaissance est privée à l’équipe. Celle-ci est partageable avec la maille. Celle-là est publique dans l’entreprise. »

Et on ne peut pas partager une connaissance sans copier le Claim ou exposer sa preuve.

---

## 2. Trois couches à ne pas confondre

| Couche | Question | Mécanisme |
|---|---|---|
| **Isolation** | « Puis-je voir cet objet ? » | `tenant_id`, RLS |
| **Autorisation** | « Ai-je le droit de le lire ? » | rôles, équipes, espaces, ACL |
| **Visibilité** | « Cet objet est-il destiné à être partagé ? » | enveloppe de connaissance |

Une ACL répond à une contrainte de sécurité. La visibilité répond à une **décision de l’owner**. Les deux doivent rester séparées.

---

## 3. Enveloppe de connaissance

Chaque objet de connaissance — `claim`, `preuve`, `fiche_vivante`, `source.exploration`, `situation` — porte :

```text
visibility     PRIVATE | TEAM | TWIN | PORTFOLIO | MESH | ENTERPRISE
classification PUBLIC | INTERNAL | CONFIDENTIAL | SECRET
publication    DRAFT | PROPOSED | REVIEWED | PUBLISHED | RETRACTED
owner_twin     twin_id
owner_team     team_id
projection     EXISTENCE | SUMMARY | EVIDENCE | FULL
published_at
published_by
valid_from
valid_to
```

### Niveaux de visibilité

| Niveau | Qui voit | Usage |
|---|---|---|
| `PRIVATE` | L’owner uniquement | Brouillon, hypothèse, analyse sensible |
| `TEAM` | L’équipe propriétaire | Connaissance interne à une équipe |
| `TWIN` | Le Twin et ses consommateurs directs | Connaissance applicative |
| `PORTFOLIO` | Un domaine ou un portefeuille | Connaissance partagée entre applications d’un domaine |
| `MESH` | Les autres Twins du tenant | Connaissance transversale |
| `ENTERPRISE` | Tous les utilisateurs authentifiés du tenant | Connaissance institutionnelle |
| `EXTERNAL` | Hors tenant | À ouvrir plus tard, avec une gouvernance séparée |

Commencer par `PRIVATE` / `TEAM` / `MESH` / `ENTERPRISE`. `EXTERNAL` est une décision produit et sécurité distincte.

### Niveaux de projection

| Projection | Ce que le consommateur reçoit |
|---|---|
| `EXISTENCE` | « Une connaissance existe sur ce sujet », owner, fraîcheur, confiance |
| `SUMMARY` | L’énoncé du Claim, maturité, confiance, fraîcheur, owner |
| `EVIDENCE` | L’énoncé + localisateurs de preuve (éventuellement expurgés) |
| `FULL` | L’énoncé + preuves + extraits + contexte |

Le consommateur reçoit le plus haut niveau autorisé par `visibility` + `classification` + ACL.

---

## 4. La publication est un objet gouverné

La publication n’est pas un booléen. C’est un objet :

```text
publication_id
claim_id
scope            TEAM | TWIN | PORTFOLIO | MESH | ENTERPRISE
projection       EXISTENCE | SUMMARY | EVIDENCE | FULL
requested_by
reviewed_by
decision         PROPOSED | APPROVED | REJECTED | RETRACTED
reason
valid_from
valid_to
signature
```

Workflow :

```text
DRAFT
  → PROPOSED      (l'owner demande à publier)
  → REVIEWED      (un reviewer de l'équipe valide)
  → PUBLISHED     (visible dans le scope)
  → RETRACTED     (l'owner retire ; l'historique reste)
```

Règles :

- un Claim `SECRET` ne quitte jamais l’owner, même en `EXISTENCE` ;
- un Claim `CONFIDENTIAL` n’est publié qu’avec une revue explicite ;
- un Claim `PUBLISHED` est **cité**, jamais copié ;
- une contradiction crée un objet `contradiction` lié à l’owner ;
- une rétractation se propage : le consommateur voit `RETRACTED` et cesse de l’utiliser ;
- la fraîcheur et la maturité sont celles de l’owner.

---

## 5. Service de projection

```python
def projeter(claim, consommateur):
    # 1. tenant
    # 2. ACL (rôle, équipe, espace)
    # 3. visibility
    # 4. classification
    # 5. publication (PUBLISHED, valide à la date)
    # 6. projection (EXISTENCE → SUMMARY → EVIDENCE → FULL)
    # 7. expurgation (secrets, PII, locators interdits)
    # 8. retour : énoncé, owner, maturité, confiance, fraîcheur, preuves autorisées
```

Le service ne copie pas le Claim. Il rend une **vue**.

---

## 6. Fiche vivante

La fiche est une **synthèse**. Elle ne doit pas devenir un contournement d’ACL.

- La fiche interne du Twin peut contenir toutes les connaissances autorisées pour l’owner.
- La fiche publiée dans la maille est générée à partir des **Claims projetés**, pas de tous les Claims.
- Une preuve `CONFIDENTIAL` n’entre jamais dans une fiche `MESH` sans expurgation.
- Chaque puce de la fiche peut porter son niveau de projection.

---

## 7. Schéma cible

```sql
ALTER TABLE claim ADD COLUMN visibility text NOT NULL DEFAULT 'PRIVATE'
  CHECK (visibility IN ('PRIVATE','TEAM','TWIN','PORTFOLIO','MESH','ENTERPRISE'));
ALTER TABLE claim ADD COLUMN classification text NOT NULL DEFAULT 'INTERNAL'
  CHECK (classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','SECRET'));
ALTER TABLE claim ADD COLUMN publication text NOT NULL DEFAULT 'DRAFT'
  CHECK (publication IN ('DRAFT','PROPOSED','REVIEWED','PUBLISHED','RETRACTED'));
ALTER TABLE claim ADD COLUMN owner_twin text;
ALTER TABLE claim ADD COLUMN owner_team text;
ALTER TABLE claim ADD COLUMN projection text NOT NULL DEFAULT 'SUMMARY'
  CHECK (projection IN ('EXISTENCE','SUMMARY','EVIDENCE','FULL'));
ALTER TABLE claim ADD COLUMN published_at timestamptz;
ALTER TABLE claim ADD COLUMN published_by text;

CREATE TABLE publication (
  id bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  claim_id bigint NOT NULL REFERENCES claim(id),
  scope text NOT NULL CHECK (scope IN ('TEAM','TWIN','PORTFOLIO','MESH','ENTERPRISE')),
  projection text NOT NULL CHECK (projection IN ('EXISTENCE','SUMMARY','EVIDENCE','FULL')),
  requested_by text NOT NULL,
  reviewed_by text,
  decision text NOT NULL DEFAULT 'PROPOSED'
    CHECK (decision IN ('PROPOSED','APPROVED','REJECTED','RETRACTED')),
  reason text,
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

---

## 8. Sécurité

Avant d’ouvrir une partie publique :

- `ACL_STRICT=1` en production ;
- `X-Espace` dérivé de l’identité, jamais du client (P0-1 du REVIEW) ;
- RLS sur `claim`, `preuve`, `fiche_vivante`, `source`, `source.exploration` ;
- `visibility = PRIVATE` par défaut ;
- `classification = INTERNAL` par défaut ;
- `publication = DRAFT` par défaut ;
- aucune publication `MESH` ou `ENTERPRISE` sans revue ;
- audit de chaque publication, projection, citation, contradiction, rétractation.

---

## 9. Tests

Matrice minimale :

| Cas | Attendu |
|---|---|
| Claim `PRIVATE` | Invisible dans la maille |
| Claim `TEAM` | Visible uniquement par l’équipe |
| Claim `MESH` + `SUMMARY` | Énoncé visible, preuves absentes |
| Claim `CONFIDENTIAL` | `EXISTENCE` seulement pour les non-autorisés |
| Claim `SECRET` | Invisible, même en `EXISTENCE` |
| Claim `RETRACTED` | Disparaît de la maille |
| Contradiction | Visible des deux côtés, owner authority |
| Fiche `MESH` | Générée uniquement depuis les Claims projetés |
| Citation | Référence, pas copie |
| Rétractation | Propage l’état `RETRACTED` |

---

## 10. Ordre d’implémentation

1. Enveloppe sur `claim` + table `publication`.
2. Service `projeter(claim, consommateur)`.
3. Vue `mesh_claims` (Claims publiés, projetés).
4. Tests de la matrice.
5. Branchement de la fiche sur `mesh_claims`.
6. UI de publication dans la revue du Twin.
7. Audit et rétractation.
8. `EXTERNAL` plus tard.

---

## 11. Questions ouvertes

1. Le « public » est-il interne au tenant (`MESH` / `ENTERPRISE`) ou externe (`EXTERNAL`) ?
2. Qui est reviewer d’une publication : l’owner, l’équipe, un rôle plateforme ?
3. Une publication peut-elle exposer une preuve `EVIDENCE` sans exposer le document source ?
4. Comment propager une rétractation aux fiches qui ont déjà cité le Claim ?
5. Quelle est la durée de validité d’une publication ?

---

## 12. Critique du modèle et alternative plus simple

La première version ci-dessus est trop lourde. Quatre axes sur chaque Claim — `visibility`, `classification`, `publication`, `projection` — produisent une matrice de 480 combinaisons dont la plupart sont invalides. Elle crée aussi deux sources de vérité : l’état sur le Claim et l’objet `publication`.

### 12.1 Publication-centric, pas Claim-envelope

- Le Claim garde : `tenant_id`, `jumeau_id`, `confidentialite` (dérivée de la preuve la plus sensible), `statut`, `maturite`.
- Il ne porte ni `visibility`, ni `publication`, ni `projection`.
- Le seul objet de partage est `claim_share` :

```text
claim_share
  claim_id
  scope_type      TEAM | TWIN | PORTFOLIO | TENANT
  scope_id
  projection      SUMMARY | EVIDENCE
  granted_by
  reviewed_by
  valid_from
  valid_to
  revoked_at
  reason
```

- `authorize(claim, consommateur)` est la seule fonction de règle. Elle est **deny-by-default** : pas de share actif, pas d’accès.
- La visibilité effective est **dérivée** des shares actifs, jamais stockée sur le Claim.
- Un Claim `SECRET` ne peut jamais avoir de share.
- Un Claim `CONFIDENTIAL` ne peut avoir qu’un share `SUMMARY`, avec revue.

### 12.2 La fiche est un rendu, pas le modèle

- L’unité de compréhension est la **question**, pas la fiche. Les sept questions ont un statut : `answered`, `partial`, `unknown`, `contradicted`.
- La fiche est un **rendu** de ces réponses. Chaque puce pointe vers un `claim_id`, pas seulement vers une citation de code.
- La fiche est invalidée quand un Claim cité est fermé, rétracté ou contredit.
- La fiche est générée **par audience** — 30 secondes, développeur, audit, CAB — à partir des Claims autorisés pour cette audience.

### 12.3 Séparer ingestion et compréhension

- L’ingestion est **déterministe et rapide** : observations, Claims structurels, couverture.
- La compréhension est un **job repris** : les sept questions, avec la méthode, après la naissance.
- Le Twin naît `COMPREHENSION_PENDING` et affiche sa couverture : « 3/7 répondu, 2 partiels, 2 inconnus ».
- La fiche n’est pas présentée comme complète tant que la couverture est faible.

### 12.4 Le public est un catalogue, pas une matrice

- Une **carte de catalogue** par Twin : identité, owner, capacités, interfaces, dépendances, fraîcheur, criticité. Déterministe, sans LLM.
- Les **résumés partagés** pour les questions transverses.
- L’accès aux preuves se **demande** et s’audite.
- C’est suffisant pour la découverte et l’impact ; les preuves complètes restent dans le Twin.

### 12.5 Ce qu’on implémente d’abord

1. `claim_share` + `authorize` + tests.
2. Les sept questions + couverture + rendu de fiche.
3. La carte de catalogue.
4. Le chat sur Claims + preuves, pas sur la fiche seule.
5. Le modèle à quatre axes et `EXTERNAL` plus tard, seulement si un cas réel l’exige.

### 12.6 Implémentation (2026-11-05)

- `backend/meridian/domain/partage.py` : `Consommateur`, `Partage`, `autoriser`, `projeter`.
- `backend/meridian/adapters/outbound/postgres/partage.py` : `accorder`, `revoquer`, `autoriser_claim`, `projeter_claim`, `claims_visibles`.
- `schema.sql` : `claim.confidentialite`, `preuve.confidentialite`, `claim_share`.
- `backend/meridian/tests/test_partage.py` : domaine + Postgres.
- `backend/meridian/domain/comprehension.py` : sept questions, `QuestionStatus`, couverture.
- `connaissances(..., consommateur=...)` : lecture projetée via `claims_visibles`.
- `backend/meridian/tests/test_comprehension.py` : statuts et couverture.
- `fiche_vivante` : colonnes `questions`, `couverture`, `claims` ; `fiche_courante` expose `stale`.
- `gardien.veiller` : calcule les sept statuts et enregistre les Claims cités.
- `comprendre.claims_cites` / `puces_avec_claims` ; `flore.fiche_affichable` expose `puces`, `claims`, `stale`.
- `flore._contexte` : `Consommateur` du twin, `connaissances` projetées, couverture/stale dans le contexte.
- `agent.mes_connaissances` : passe le consommateur ; `lire_code`/`chercher_dans`/`lire_dans`/`cbm_outil` refusent une lecture hors twin.
- `prompt_systeme` : affiche la couverture et la fiche à revérifier.
- `carte.py` : carte de catalogue enrichie — type, `application_id`, périmètre, owner, criticité, couverture, fraîcheur, dépendances business ; `carte_du_jumeau` accepte un consommateur et projette les Claims.
- `depot.jumeau_carte` ; `fiche_courante` expose `cree_le`.
- Vérification : **159 passed, 4 skipped** (fiche/partage/compréhension) ; **93 passed, 1 skipped** (chat/fiche) ; **62 passed** (harness/orchestrateur/mobilisation/retrieval) ; **83 passed, 1 skipped** (carte/fiche/poignée/flore/partage) ; **53 passed, 3 skipped** (examen/naissance).
- `retrieval_memoire`, `memoire_dialogue`, `retrieval_chat`, `cases.py`, `analyse_service`, `analyse_runtime` : le consommateur est transmis jusqu'aux Claims.
- `interfaces.py` : `_consommateur_requete` (tenant + espace authentifiés), `GET /v2/jumeaux/{id}/carte` (partages), `POST /v2/jumeaux/{id}/carte/publier` et `/depublier`.
- `partage.publier_carte` / `depublier_carte` : publication explicite, `SECRET` ignoré, `CONFIDENTIAL` avec revue, pas de doublon.
- Décision : la carte n'est **pas publique par défaut**. L'owner publie les Claims métier en `SUMMARY` ; les métadonnées (identité, owner, fraîcheur, criticité) restent visibles au tenant.
- `interfaces.py` : `_peut_publier` (démo, rôle, autorité ou équipe propriétaire), `PublicationCarte` (`reviewed_by`, `scope`, `scope_id`), auto-revue refusée ; `GET /carte?audience=business|architecture|audit&technique=...`.
- `carte.perimetre_autorise` : slug du périmètre déclaré vs `portfolio_id` authentifié ; `carte_du_jumeau` refuse un autre périmètre.
- `auth.py` : `request.state.role` et `request.state.equipe` depuis l'identité locale/OIDC.
- `carte.dependances_techniques` : uniquement en lentille `architecture` ou `technique=true`.
- Vérification : **131 passed, 1 skipped** (carte/partage/gardien/flore/poignée/retrieval/analyse/connaissance/compréhension).
- Reste : flux d'identité externe, backfill `perimetre_id`, UI de revue, source de rôle/équipe au-delà du poste.

### 12.7 Durcissement (2026-11-05)

- Rôles : `_peut_publier` mappe `product_owner`/`architecte`/`admin` sur `APPLICATION_OWNER`/`PORTFOLIO_OWNER`/`TENANT_ADMIN`, et accepte `autorite=decision|approbation` ou l'équipe propriétaire.
- Périmètre : `jumeau.perimetre_id` prime sur `perimetre` ; `carte.perimetre_autorise` normalise les slugs ; `_consommateur_requete` utilise `request.state.perimetre` puis `espace`.
- `auth.py` expose `role`, `equipe` et `perimetre` depuis l'identité locale/OIDC.
- `PublicationCarte.scope` accepte `EXTERNAL`, sous réserve du flag `JUMEAU_EXTERNAL_PUBLICATION`.
- `EXTERNAL` est **deny-by-default** : `accorder` et `publier_carte` le refusent tant que le flag est faux ; `scope_correspond` ne consomme pas encore un consommateur externe.
- `publication_review` trace chaque partage `CONFIDENTIAL` effectif (Claim ou preuve) : reviewer, décision, raison, date.
- `jumeau.perimetre_id` est ajouté ; `carte.perimetre_autorise` le préfère au texte libre.
- `retrieval_memoire` : `twin_proprietaire` ; vue propriétaire seulement si le Twin sélectionné est explicitement propriétaire, sinon lecture via `claim_share`.
- `cases.py` / `analyse_service.py` passent le Twin unique de la sélection comme `twin_proprietaire` ; sinon `None`.
- `publication_review` est couvert par RLS.
- Tests : `test_carte.py` + `test_interfaces_http.py` = **16 passed** ; `test_partage.py` = **43 passed** ; `test_partage + carte + interfaces + flore + poignée + gardien` = **114 passed, 1 skipped** ; `test_retrieval_memoire.py` = **17 passed** ; suite combinée finale = **232 passed, 4 skipped**.

### 12.8 Dernières limites (2026-11-05)

- **EXTERNAL est parké** : le domaine connaît le scope et `Consommateur.external_id`, la publication reste deny-by-default, et l'API ne l'expose pas. Le flux d'identité externe est **hors périmètre pour le moment**.
- **`perimetre_id`** : `slug_perimetre`, `construire_identite`, `commandes`, `naissance`, `depot.enregistrer` et `creer_jumeau` ; les Twins existants sans `perimetre_id` restent en fallback `perimetre`.
- **Rôles ADR-0001** : `domain/roles.py` ; `administrateur` → `TENANT_ADMIN`, `product_owner` → `APPLICATION_OWNER`, `architecte` → `PORTFOLIO_OWNER`.
- **Revue** : `lister_a_reviser`, `decider_revue`, `GET /carte/a-reviser`, `POST /carte/revue`, trace `publication_review`.
- **Tests live** : `legacy.generer_tour` ne transmet plus `autoriser_ecriture` ; `test_cases_flore` est auto-suffisant ; instance isolée `meridian_test` = **13 passed, 2 skipped**.
- **Vérification finale** : **260 passed, 4 skipped** (canonique) ; **9 passed** (auth) ; **13 passed, 2 skipped** (live isolé).
- **Reste, strictement interne** : backfill `perimetre_id`, UI de revue, invitations `equipes`, et exécution reproductible des tests live.

### 12.9 Équipe issue de l'identité (2026-11-05)

- `auth.py` expose `equipes` : `equipes`/`equipe`/`equipe_id` pour l'identité locale, `equipes`/`groups`/`teams` pour OIDC.
- L'invitation locale peut porter `equipes` ou `equipe_id` ; le compte les conserve.
- `_peut_publier` accepte l'équipe propriétaire du Twin si elle figure dans `equipes`, en plus du rôle et de l'autorité.
- Tests : `test_interfaces_http.py` + `test_auth.py` = **16 passed**.
- Reste : remplir `equipes` dans les invitations existantes et, si nécessaire, dans l'écran d'invitation.

### 12.10 Backfill et revue UI (2026-11-05)

- `backend/meridian/application/backfill_perimetre.py` + `scripts/backfill-perimetre-id.py` : dry-run par défaut, `--apply`, `--tenant`, `--limite`, idempotent, ne remplace jamais une valeur existante.
- Dry-run dev : 1 Twin à migrer (`app-mw2pjdfi75vi -> omega`), 7 ignorés sans périmètre. Aucun `--apply` sur une base réelle.
- `frontend/src/pages/RevuePublication.jsx` : file `a-reviser`, Approuver/Rejeter avec raison, rafraîchissement, états vide/erreur, contrôle des quatre yeux.
- Route `/revue-publication` + entrée de navigation.
- Tests frontend : **41 suites, 231 tests**.
- Vérification backend combinée : **338 passed, 4 skipped** ; live isolé : **13 passed, 2 skipped**.

---

## 13. Références

- `docs/architecture/ecosysteme-tiers.md` — « une vue transverse est une projection autorisée ».
- `docs/adr/0030-ecosysteme-tiers-identite.md` — ACL de source, identité `twin_id`.
- `docs/MERIDIAN_Knowledge_Claims_Architecture_v1.md` — `ClaimScope`, `ClaimOrigin`, `ClaimStatus`, `ClaimMaturity`.
- `docs/MERIDIAN_Domain_Model_Information_Architecture_v1.md` — famille « Interaction & gouvernance ».
- `docs/application-twin.md` — classification `public / interne / confidentiel / secret`.
