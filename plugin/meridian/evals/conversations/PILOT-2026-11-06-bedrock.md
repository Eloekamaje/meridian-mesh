# Pilote Bedrock réel — 2026-11-06

## Question

Le benchmark conversationnel peut-il tourner sur le **vrai Bedrock**, avec un compte AWS
réel, des embeddings réels et des modèles réels — et que mesure-t-il alors ?

Ce pilote répond aussi à la question préalable : **Floci** peut-il servir à cette
validation ? Non : son Bedrock Runtime est un stub (ou un proxy vers un endpoint
OpenAI-compatible), pas une inférence Bedrock. Voir
[`docs/architecture/floci-evaluation.md`](../../../../docs/architecture/floci-evaluation.md).

## Compte et résidence

- Compte AWS réel du profil `default` (compte `990508469794`, utilisateur `itadmin`),
  credentials de `~/.aws/credentials`.
- Région Bedrock : **`ca-central-1`**.
- Un second profil `meridian-bedrock` (compte `267949810690`, utilisateur `majella`) a
  été configuré ensuite ; son Bedrock Runtime est encore bloqué par la vérification du
  compte, voir la section « Nouveau compte » en fin de document.
- Embeddings : `amazon.titan-embed-text-v2:0`, 1024 dimensions, déjà validés par
  [`../retrieval/PILOT-2026-11-06.md`](../retrieval/PILOT-2026-11-06.md).
- Aucun secret n'est écrit dans le dépôt ; les identifiants de benchmark sont des comptes
  locaux de test.

## Accès réel aux modèles (constaté le 2026-11-06)

| Modèle | Type | `Converse` | `ConverseStream` | Tool use en streaming | Résidence |
|---|---|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | embeddings | ✅ 1024 dims | — | — | `ca-central-1` |
| `ca.amazon.nova-lite-v1:0` | chat | ✅ | ✅ | ✅ | profil CA |
| `anthropic.claude-3-sonnet-20240229-v1:0` | chat | ✅ | ❌ formulaire d'usage Anthropic | non testé | `ca-central-1` |
| `anthropic.claude-3-haiku-20240307-v1:0` | chat | ⚠️ instable (un appel a réussi, puis formulaire d'usage) | ❌ | — | `ca-central-1` |
| `ca.anthropic.claude-haiku-5-5` | chat | ❌ instrument de paiement Marketplace | ❌ | — | profil CA |
| `mistral.mistral-large-2402-v1:0` | chat/juge | ✅ | ✅ | ❌ (« doesn't support tool use in streaming mode ») | `ca-central-1` |
| `meta.llama3-70b-instruct-v1:0` | chat | ✅ | ✅ | ❌ | `ca-central-1` |
| `mistral.mistral-7b-instruct-v0:2` | chat | ✅ | ✅ | non testé | `ca-central-1` |
| `meta.llama3-8b-instruct-v1:0` | chat | ✅ | ✅ | non testé | `ca-central-1` |

Deux blocages empêchent d'utiliser les modèles Anthropic comme modèle principal :

1. **Formulaire d'usage Anthropic** : `Claude 3 Sonnet` répond en `Converse` mais refuse
   `ConverseStream` (« Model use case details have not been submitted for this account »).
   Or Strands utilise le streaming pour l'agent et ses outils.
2. **Instrument de paiement Marketplace** : `Claude Haiku 5.5` renvoie
   `INVALID_PAYMENT_INSTRUMENT` (« A valid payment instrument must be provided »).

Les modèles Mistral/Llama ne savent pas faire de tool use en streaming. Le seul modèle
canadien disponible qui combine **streaming + tool use** est donc
`ca.amazon.nova-lite-v1:0`. C'est un modèle de repli, pas le modèle cible.

Les profils `global.*` et `us.*` existent pour les modèles récents, mais ils routent hors
Canada : ils n'ont pas été utilisés pour ne pas violer la résidence `ca-central-1`.

### Piste sans Claude : Mistral Large

Mistral Large est un modèle canadien plus fort que Nova Lite. Il **sait faire du tool use
en `Converse` non-streaming** : un appel direct avec `toolConfig` rend bien un bloc
`toolUse` (`stopReason=tool_use`). Strands sait aussi convertir une réponse non-streaming
en événements (`streaming=False`), et `agent.py` bascule automatiquement Mistral/Llama
dans ce mode.

Mais dans l'agent Flore complet, Mistral Large a produit les appels d'outils **en texte
JSON** dans la réponse :

```text
[{"name": "resoudre_application", "arguments": {"terme": "conduit"}}]
```

L'agent ne les exécute donc pas. Ce n'est pas un problème d'accès Bedrock : c'est un
problème d'adaptation du harness (prompt, choix d'outil forcé ou parsing sûr des appels
textuels). Mistral Large n'est pas encore un remplacement direct de Claude pour le rôle
d'orchestrateur. Llama/Mixtral, eux, ne supportent pas du tout le tool use via Bedrock
`Converse`.

Un autre essai, **hors résidence canadienne**, utilise GPT-OSS 120B en `us-east-1` :
26/33 (79 %) aux critères déterministes et 67 % au juge. GPT-OSS est disponible en
`us-east-1` seulement, pas en `ca-central-1` ; voir
[`PILOT-2026-11-06-gptoss-us-east-1.md`](PILOT-2026-11-06-gptoss-us-east-1.md).

**Kimi K3** est également accessible via les profils `us.`/`global.` (donc hors Canada) :
9/11 (82 %) aux critères déterministes et 8/11 au juge, mais **87 s de moyenne** par
scénario, jusqu'à 3,5 min. Voir
[`PILOT-2026-11-06-kimi-k3-us-east-1.md`](PILOT-2026-11-06-kimi-k3-us-east-1.md).

## Correctifs nécessaires pour que Bedrock fonctionne

Le chemin Bedrock n'avait jamais été exercé de bout en bout ; trois défauts sont apparus :

1. `agent.py` passait à la fois `boto_session` et `region_name` à `Strands.BedrockModel` :
   Strands refuse cette combinaison (`Cannot specify both region_name and boto_session`).
   La session porte déjà la région ; `region_name` a été retiré.
2. Aucun plafond de sortie n'était posé : un modèle à raisonnement pouvait épuiser sa
   réponse avant de conclure. `JUMEAU_MAX_TOKENS` (défaut 4096) est maintenant transmis.
3. Nova Lite émet des blocs `<thinking>…</thinking>` visibles. Ils sont retirés de la
   réponse finale (`agent.sans_raisonnement`) ; si le modèle ne produit que du
   raisonnement, l'orchestrateur retourne `None` et le repli déterministe sur le jumeau
   sélectionné s'applique, au lieu d'afficher un raisonnement vide.

La relecture utilise désormais le **modèle juge** (`BEDROCK_MODEL_JUDGE`) quand il est
configuré, et non le modèle de l'auteur : un modèle faible ne doit pas valider ses propres
manques de citations.

Le benchmark accepte un fournisseur Bedrock pour le baseline et le juge :

```bash
export MERIDIAN_BENCH_EMAIL='benchmark@meridian.local'
export MERIDIAN_BENCH_PASSWORD='<mot-de-passe-local>'
export MERIDIAN_BENCH_PILOT_EMAIL='benchmark-pilot@meridian.local'
export MERIDIAN_BENCH_PILOT_PASSWORD='<mot-de-passe-local>'

backend/.venv/bin/python plugin/meridian/evals/conversations/run.py \
  --fournisseur bedrock \
  --modele ca.amazon.nova-lite-v1:0 \
  --modele-juge mistral.mistral-large-2402-v1:0 \
  --runs 3 \
  --output /tmp/conversations-bedrock
```

L'API doit tourner avec :

```bash
JUMEAU_MODELE=bedrock \
BEDROCK_MODEL_CHAT=ca.amazon.nova-lite-v1:0 \
BEDROCK_MODEL_JUDGE=mistral.mistral-large-2402-v1:0 \
JUMEAU_MAX_TOKENS=4096 \
backend/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
```

## Protocole

- 11 scénarios, 3 runs chacun = **33 tours évalués**.
- Flore : API Méridian réelle, `JUMEAU_MODELE=bedrock`, chat
  `ca.amazon.nova-lite-v1:0`.
- Baseline : le **même modèle**, appelé directement sans outils ni connaissances Méridian.
- Juge : `mistral.mistral-large-2402-v1:0`, à l'aveugle (ordre A/B aléatoire).
- Critères déterministes inchangés : présence de faits, preuve localisée, abstention,
  refus, action non exécutée.

## Résultats

| Indicateur | Flore + Méridian (Nova Lite) | Assistant seul (Nova Lite) |
|---|---:|---:|
| Critères déterministes | **13/33 (39 %)** | 7/33 (21 %) |
| Pass@k | **64 %** | 27 % |
| Durée moyenne | 10,9 s | 1,8 s |
| Jugements | **23 victoires, 3 défaites, 7 égalités** | — |
| Taux de victoire au juge | **70 %** (IC95 54–85 %) | — |

### Comparaison avec le pilote DeepSeek

| Modèle de Flore | Déterministe | Pass@k | Juge |
|---|---:|---:|---:|
| DeepSeek (pilote précédent) | 30/33 (91 %) | 100 % | 28/33 (85 %, IC95 73–97 %) |
| Bedrock GPT-OSS 120B (`us-east-1`) | 26/33 (79 %) | 100 % | 22/33 (67 %, IC95 51–83 %) |
| Bedrock Kimi K3 (`us.`/`global.`, 1 run) | 9/11 (82 %) | 82 % | 8/11 (73 %, IC95 46–99 %) |
| Bedrock Nova Lite (ce pilote) | 13/33 (39 %) | 64 % | 23/33 (70 %, IC95 54–85 %) |

Le même harness, sur les mêmes scénarios, perd **52 points de critères déterministes**
avec Nova Lite. Ce n'est pas un défaut du harness : c'est le modèle qui n'appelle pas les
outils de code et ne produit pas les citations attendues.

**Contrôle de non-régression DeepSeek** : après les correctifs Bedrock, un run de contrôle
avec `JUMEAU_MODELE=deepseek` donne **10/11 (91 %) aux critères déterministes** et
**10/11 au juge**. Le harness n'a donc pas été dégradé par les changements ; l'écart
Bedrock est bien porté par le modèle.

Une **comparaison équitable** (juge unique Mistral Large, 3×11 runs, température 0 quand
le modèle l'accepte) confirme : DeepSeek 33/33 (100 %) et 29/33 au juge, GPT-OSS 24/33
(73 %) et 26/33 (79 %), Nova Lite 16/33 (48 %) et 21/33 (64 %), Kimi K3 11/11 et 10/11
(1 run, 101 s). Voir [`PILOT-2026-11-06-equitable.md`](PILOT-2026-11-06-equitable.md).

### Nature des échecs

- **`must_cite_evidence`** domine : la réponse est souvent plausible mais sans
  `chemin#Ldébut-Lfin`. Nova Lite répond depuis le contexte/claims sans appeler les
  outils de code, et la relecture Mistral ne parvient pas à lui faire ajouter les
  citations.
- **`conduit-dependencies`** : FastAPI/PostgreSQL ne sont pas nommés, alors que le claim
  et la preuve existent.
- **`conduit-false-premise`** : la négation de « est arrêtée » n'est pas tenue ; le modèle
  laisse une occurrence affirmée.
- **`conduit-unknown-metric`** : l'abstention n'est pas reconnue (le modèle propose une
  mesure au lieu de dire qu'elle n'existe pas).
- **`securite` et `action`** restent à 100 % : le refus d'injection, l'isolation tenant et
  le contrat d'action ne dépendent pas de la finesse du modèle.

Le juge aveugle préfère néanmoins Flore dans 70 % des cas : même avec un modèle faible,
le contexte, les claims et les garde-fous apportent de la valeur par rapport au même
modèle seul. Mais **on ne peut pas conclure que Méridian atteint 91 % avec Bedrock** :
le modèle cible n'était pas accessible.

## Ce que ce pilote prouve

- Bedrock réel fonctionne pour les **embeddings** (Titan V2, 1024 dims, `ca-central-1`).
- Bedrock réel fonctionne pour le **chat** et le **tool use** avec Nova Lite canadien.
- Le benchmark peut opposer Flore et un baseline **du même modèle Bedrock**, jugé par un
  modèle d'une autre famille (Mistral Large), sans secret dans le dépôt.
- Les défauts d'intégration Bedrock (session/région, plafond de sortie, raisonnement
  visible) sont corrigés et testés.
- Floci n'aurait rien prouvé de tout cela : il ne fait pas d'inférence réelle.

## Limites et prochaines étapes

1. **Soumettre le formulaire d'usage Anthropic** dans la console Bedrock (Model access)
   et vérifier l'instrument de paiement Marketplace. C'est un prérequis pour
   `Claude 3 Sonnet`/`Claude 3 Haiku` en streaming et pour `Claude Haiku 5.5`.
2. Rejouer le même benchmark avec `anthropic.claude-3-sonnet-20240229-v1:0` ou
   `ca.anthropic.claude-haiku-5-5` dès que le streaming est autorisé. On attend un
   résultat plus proche des 91 % DeepSeek.
3. Ne pas utiliser les profils `global.*`/`us.*` pour le pilote canadien : ils routent
   hors Canada.
4. Envisager un **gate de citation** déterministe pour les réponses de jumeau : si des
   sources existent et que la réponse n'en cite aucune, demander une révision avant
   envoi. À concevoir sans inventer de preuve.
5. Floci reste réservé à un smoke test CI de plomberie AWS, opt-in, avec credentials
   factices et réponses stub assumées.

## Nouveau compte `meridian-bedrock` (2026-11-06)

- Profil `meridian-bedrock` configuré : région `ca-central-1`, sortie `json`.
- Identité : compte **`267949810690`**, utilisateur IAM **`majella`**.
- Le plan de contrôle Bedrock répond : 49 modèles, 62 profils d'inférence, dont
  `ca.amazon.nova-lite-v1:0` et `ca.anthropic.claude-haiku-5-5` en `ACTIVE`.
- Le runtime est **partiellement accessible** pendant la vérification :
  - `amazon.titan-embed-text-v2:0` : ✅ 1024 dimensions ;
  - `mistral.mistral-large-2402-v1:0` : ✅ `Converse` et `ConverseStream` (pas de tool use) ;
  - `ca.amazon.nova-lite-v1:0` : ✅ `ConverseStream` + tool use ; `Converse` échoue par
    intermittence avec « Your account is currently being verified » ;
  - `anthropic.claude-3-haiku-20240307-v1:0` et `claude-3-sonnet` : `ConverseStream`
    refusé par le formulaire d'usage Anthropic ;
  - `ca.anthropic.claude-haiku-5-5` : « not available for this account » / vérification.
- La vérification AWS est annoncée sous moins de 2 heures ; certains appels `Converse`
  échouent encore. Il faut attendre avant de conclure sur ce compte.
- Aucun benchmark complet n'a été relancé sur ce compte. Le pilote ci-dessus reste celui
  du compte `990508469794`.
- Prochaine action : attendre la fin de la vérification AWS, soumettre le formulaire
  d'usage Anthropic, puis relancer :

  ```bash
  AWS_PROFILE=meridian-bedrock backend/.venv/bin/python scripts/verifier-bedrock.py
  ```

## Artefacts

```text
plugin/meridian/evals/conversations/pilots/2026-11-06-bedrock/REPORT.md
plugin/meridian/evals/conversations/pilots/2026-11-06-bedrock/REPORT-run1.md   # run préparatoire (1×11)
plugin/meridian/evals/conversations/pilots/2026-11-06-bedrock/summary.json
/tmp/opencode/conversations-bedrock-final/REPORT.md
/tmp/opencode/conversations-bedrock-final/summary.json
```

## Vérifications

```text
Backend ciblé (honnêteté, raisonnement, citation, orchestrateur, architecture) : 44 passed
Plugin / benchmarks                                                             : 62 passed
Contrôle DeepSeek (1×11)                                                        : 10/11 déterministe, 10/11 juge
Vérificateur Bedrock (`scripts/verifier-bedrock.py`)                            : opérationnel sur les deux profils
API health                                                                      : 200
```
