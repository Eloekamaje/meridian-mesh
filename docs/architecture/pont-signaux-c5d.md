# Pont C5d — Signaux canoniques

> **Statut :** opérationnel en création, liste et lecture, périmètre UI borné.
> **Dernière mise à jour :** 8 novembre 2026.

## Objet

`Signal` est un objet d'entreprise canonique (`famille = emergence`) qui consigne un
événement, un changement, une dérive, une anomalie, une contradiction, une opportunité, un
risque ou une observation, avec une **source obligatoire**. Il ne remplace ni une
`Situation`, ni une `Expression`, ni une `Hypothesis` : c'est le fait observé qui peut
ensuite être rattaché à une ou plusieurs Situations.

Le domaine existait avant C5d (`backend/meridian/domain/objets_exploitation.py`). C5d
expose les commandes applicatives, le port, les routes, la lecture de chaîne et l'UI, sans
ajouter de cycle de transition.

## Identité et empreinte

- Table : `objet_entreprise`, type `SIGNAL`, comme tous les objets canoniques.
- Le serveur force `statut=DETECTED` et `mode=OBSERVED`.
- `id`, `tenant_id`, `fingerprint`, `statut` et `mode` sont serveur : un client qui les
  envoie est refusé en 422.
- `source` et `libelle` sont obligatoires et non vides.
- `type_signal` optionnel, défaut `OBSERVATION`, validé contre `TYPES_SIGNAL`.
- `fingerprint` est calculé **avant toute écriture**, jamais accepté du client.

Règle d'empreinte (documentée et testée dans le domaine) :

```text
sha256("signal-v1\x1f" + canon(source) + "\x1f" + canon(type_signal)
       + "\x1f" + canon(libelle) + "\x1f" + canon(detecte_le))
```

`canon` applique NFKC, compacte les espaces (une suite d'espaces devient un espace) et
replie la casse. Une `detecte_le` absente vaut la **chaîne vide** : l'heure serveur n'entre
jamais dans l'empreinte. Deux créations identiques, avec la même date ou sans date,
produisent donc la même empreinte et la seconde répond **409**, y compris sous concurrence
réelle (verrou consultatif `pg_advisory_xact_lock` + contrôle d'existence dans la même
transaction). Un 409 n'est jamais un 500.

La date ISO est utilisée telle que fournie (après normalisation de texte, pas de
reformattage sémantique de fuseau) : deux écritures différentes de la même instantanéité
peuvent donc produire deux empreintes distinctes.

**Piège documenté — date serveur hors empreinte.** Lorsque `detecte_le` est absent,
l'empreinte utilise la chaîne vide, mais le domaine renseigne `detecte_le` avec l'instant
d'observation pour l'affichage. Rejouer la réponse créée en renvoyant ce `detecte_le`
serveur transforme donc la date implicite en date explicite : l'empreinte diffère et un
**second Signal** est créé (201), au lieu du 409 attendu pour un double clic sans date.
L'UI ne renvoie jamais la date d'un objet existant dans un nouveau formulaire, mais un
client API qui rejoue la réponse complète doit omettre `detecte_le` pour conserver
l'idempotence. C'est une limite assumée du contrat C5d, caractérisée par un test.

## Chaîne et persistance

```text
SITUATION → SIGNAL          (exactement une Situation liée)
SIGNAL                      (aucune Situation, ou plusieurs)
```

- Lien inverse `Situation.signal_ids` (liste), posé par la persistance d'exploitation
  dans la même transaction que le Signal. Un Signal peut porter plusieurs Situations ;
  toutes sont verrouillées et vérifiées avant écriture.
- `GET /api/boucle/objets/{id}?historique=true` accepte `SIGNAL`. La chaîne amont n'est
  exposée que si `situation_ids` contient **exactement un** élément ; un Signal
  multi-Situation ou global est un objet **sans chaîne amont**, sans erreur.
- Lecture : `SIGNAL` est ajouté à `_CLASSES_LECTURE` / `TYPES_LECTURE`, jamais à
  `TYPES_BOUCLE`. `enregistrer_boucle` refuse toujours ce type.

## API

| Méthode | Route | Réponse |
|---|---|---|
| `POST` | `/api/boucle/signals` | 201 `ReponseTransition` (`type=SIGNAL`, `role=signal`) |
| `POST` | `/api/boucle/situations/{sid}/signals` | 201 `ReponseTransition`, Situation forcée |
| `GET` | `/api/boucle/signals?situation_id=&type_signal=&statut=&limite=` | liste tenant |

Corps de création strict (`extra="forbid"`) : `libelle` obligatoire, `source` obligatoire,
`type_signal`, `description`, `intensite` (0..1), `detecte_le` (ISO 8601),
`situation_ids`, `entite_ids`, `liens`, `preuves`, `confiance` (0..1).

Depuis `POST /situations/{sid}/signals`, `situation_ids` peut être absent ; s'il est
présent, il doit correspondre exactement à `[sid]` (sinon 422). En global, `situation_ids`
est optionnel et peut contenir plusieurs identifiants.

Erreurs :

- 404 : Situation absente ou hors tenant ;
- 409 : empreinte de Signal déjà connue (doublon) ;
- 422 : validation, type inconnu, champ serveur ou champ inconnu ;
- 400 : secret dans `preuves`/données non sérialisables, jeton brut au sens de la
  détection stricte, ou JSON malformé. La détection couvre **le `titre` persisté, l'`id`
  fourni, le `tenant` (brut et normalisé) et toutes les chaînes de `donnees`** (source,
  libellé, description, preuves…). Formes reconnues : JWT `eyJ…`, `gh[pousr]_…`,
  `github_pat_…`, `sk-`/`sk-proj-` d'au moins 16 caractères après le préfixe et contenant
  au moins un chiffre (`sk-abc123456789012345` est refusé), `xox[baprs]-…`, `AKIA…`, et
  `Bearer <jeton>`. Pour `Bearer`, le token capturé est de la **prose** si, en
  minuscules, il appartient à une courte liste technique (`authentication`, `authorization`,
  `token`, `scheme`, `header`, `flow`, `type`, `credentials`, `access`, `request`,
  `response`, `client`, `server`, `resource`, `endpoint`, `method`, `framework`, `library`,
  `interface`, `application`, `service`, `system`, `security`, `support`, `usage`, `mode`,
  `policy`, `standard`, `protocol`, `format`) **ou** s'il est purement alphabétique et se
  termine par un suffixe technique (`tion`, `sion`, `ment`, `ity`, `ance`, `ence`, `ing`,
  `ed`, `al`, `ive`, `ous`, `able`, `ible`, `er`, `or`, `ics`, `ology`, `graphy`, `ness`,
  `ship`, `hood`, `ism`, `ist`, `ize`, `ise`). Un composé est découpé sur `-`, `/`, `_`
  et `.` ; il est prose seulement si **tous** ses segments non vides le sont. Ainsi
  `implementation`, `documentation`, `specification`, `interoperability`,
  `configuration`, `verification`, `validation`, `authentication-based`,
  `authentication/authorization`, `authentication_based` et `implementation-based`
  passent, tandis que `Bearer abcdefghijklmnop` et `Bearer abc-defghijklmnop` restent
  refusés. `sk-learn-tutorial` est accepté. Un identifiant long contenant un chiffre
  (`sk-mon-projet-2026-01`) peut être refusé : faux positif assumé. Le masquage HTTP
  utilise la même détection stricte, donc la prose `Bearer authentication` reste lisible.
  La détection n'est **pas exhaustive** : un secret opaque sans préfixe connu peut passer
  (limite caractérisée par test). Un jeton purement alphabétique finissant par un suffixe
  technique (`…er`, `…tion`, etc.) est classé prose même s'il ressemble à un jeton : faux
  négatif assumé, caractérisé par test ;
- 501 : `Idempotency-Key` (aucun stockage d'idempotence durable) ;
- 503 : Postgres indisponible.

Aucune route de changement de statut n'existe en C5d : les statuts `STATUTS_SIGNAL`
existent dans le domaine pour la suite, mais l'API et l'UI n'exposent ni transition ni
formulaire de statut.

## UI

- Bouton global « Enregistrer un signal » dans l'en-tête de la Boucle.
- Action contextuelle « Enregistrer un signal » depuis une Situation ; la route liée est
  forcée et le champ `situation_ids` est masqué.
- Formulaire `ModaleTransition` : `libelle`, `source`, `type_signal`, `description`,
  `intensite`, `detecte_le`, `situation_ids` en CSV pour le global, `preuves`,
  `confiance`. Aucun champ statut, mode, id ou empreinte.
- Après succès : sélection du Signal, ajout à la liste, refetch du parent pour exposer
  `signal_ids`, affichage de la chaîne amont disponible.
- Un 409 doublon est traduit en message lisible (« Signal déjà enregistré : un signal
  identique existe déjà. ») et garde la modale ouverte ; 400/404/422/503 sont lisibles ;
  un réseau ou un 5xx reste annoncé comme incertain.
- `TYPES_SIGNAL` est exporté par `boucleUi.js` comme source de vérité testable ; `SIGNAL`
  est un stade et un filtre de `TYPES_LECTURE`.

## Tests

- Domaine : normalisation et déterminisme de l'empreinte, indépendance à l'horloge.
- Commandes : création globale, depuis une Situation, multi-Situation, liens inverses,
  doublon, champs serveur, 404, atomicité.
- HTTP : contrat 201, validation 422, doublon 409, secret/non-JSON/jeton brut 400, 501, 503,
  liste filtrée et isolation tenant.
- Sécurité : les jetons bruts au sens de la détection stricte sont refusés avant écriture
  dans le `titre` persisté, l'`id`, le `tenant` brut/normalisé et toutes les chaînes de
  `donnees` (`preuves`, `source`, `libelle`, `description`…) ; la réponse HTTP les masque
  avec la même politique. La prose `Bearer authentication`/`Bearer implementation`/
  `Bearer documentation`/`Bearer specification` et `sk-learn-tutorial` reste acceptée.
- Migration legacy : un document dont le titre porte un jeton n'est pas migré ; le
  rapport le compte dans `erreurs`, sans crash ni réécriture. Le cas `id`/`donnees` legacy
  n'est pas couvert par un test dédié.
- Limite : un secret opaque sans préfixe connu peut passer ; un test 201 le caractérise.
- Faux négatif de forme : un jeton purement alphabétique finissant par un suffixe
  technique (`Bearer abcdefghijklmner`) est classé prose ; test unitaire dédié.
- `titre` : la colonne texte est contrôlée séparément de `donnees`, avec les mêmes motifs.
- `id` et `tenant` : un jeton dans l'identifiant fourni, le tenant brut ou le tenant
  normalisé (`demo→local`) est refusé avant persistance ; les identifiants normaux
  (`sit-…`, `dec-…`, `local`, `demo`) restent acceptés.
- Périmètre des contrôles : ils s'appliquent à la persistance canonique
  `objet_entreprise` via `entreprise_depot`. Les autres stores (mémoire, dossiers,
  sessions, Mongo legacy) ne sont pas couverts par cette barrière.
- Migration legacy : le cas testé est un `titre` porteur de jeton, non migré et reporté
  dans `erreurs`. Les documents legacy dont l'`id` ou les `donnees` portent un jeton ne
  sont pas couverts spécifiquement par ce test ; la politique de skip reste la même
  lorsqu'ils atteignent la persistance canonique.
- Rejeu : un test caractérise le second Signal créé lorsqu'on renvoie explicitement le
  `detecte_le` serveur d'une première création sans date.
- Postgres réel (opt-in `JUMEAU_PG_DSN`) : chaîne `SITUATION → SIGNAL`, absence de chaîne
  multi/global, concurrence par threads avec une seule écriture, isolation tenant,
  atomicité du lien inverse.
- Frontend : client API, action globale et contextuelle, validation libellé/source,
  doublon 409, filtre/stade SIGNAL, chaîne mono-Situation, absence de chaîne multi.

## Limites

- Création manuelle uniquement : aucun pipeline automatique de détection, de déduplication
  sémantique ou de promotion vers Expression/Hypothesis.
- Pas de route ni d'UI de changement de statut, de fusion, de rejet ou de suppression.
- Un Signal multi-Situation ou global n'a pas de chaîne amont unique ; ce n'est pas une
  erreur, mais l'UI n'affiche alors aucune étape amont.
- L'empreinte est volontairement textuelle : deux dates équivalentes écrites différemment
  restent deux composantes différentes.
- La date serveur remplie quand `detecte_le` est absent n'entre pas dans l'empreinte
  initiale ; rejouer cette date dans une nouvelle requête crée un second Signal (piège
  documenté ci-dessus, non corrigé sans changer le contrat).
- Les jetons bruts sont refusés à l'écriture selon une détection stricte ; un corpus
  legacy déjà stocké reste masqué en lecture mais n'est pas migré. La détection peut
  refuser un identifiant métier ressemblant à un jeton long contenant un chiffre
  (`sk-mon-projet-2026-01` par exemple) : faux positif assumé.
- La détection couvre les formats de credentials connus, pas les secrets opaques sans
  préfixe : un tel secret peut être accepté (limite caractérisée par test).
- Migration legacy : un document dont le `titre` porte un jeton n'est pas migré ; le
  backfill le compte dans `erreurs`, ne réécrit rien et ne migre aucun secret. Un dry-run
  le signale de la même manière, sans écriture.
- Pas de rattachement automatique des Signaux aux Expressions, Investigations ou
  Décisions au-delà de `situation_ids` et des liens libres.
