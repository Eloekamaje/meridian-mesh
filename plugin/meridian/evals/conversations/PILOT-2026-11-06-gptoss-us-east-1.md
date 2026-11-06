# Pilote GPT-OSS / us-east-1 — 2026-11-06

> **Comparaison équitable** : le pilote [`PILOT-2026-11-06-equitable.md`](PILOT-2026-11-06-equitable.md)
> reprend GPT-OSS avec un juge unique, 3×11 runs et température 0 : **24/33 (73 %)** aux
> critères déterministes et **26/33 (79 %)** au juge. Le présent document conserve les
> conditions du premier test (température par défaut).

## Question

Peut-on éviter Claude en utilisant les modèles **GPT** de Bedrock, en `us-east-1` ?
Quels modèles sont réellement accessibles, et que vaut Flore avec eux ?

## Accès réel (profil `meridian-bedrock`, compte `267949810690`)

### Modèles GPT propriétaires

Les modèles GPT-5/5.5/5.6/6/6.1 existent au catalogue, mais ne sont **pas accessibles**
au compte, même via les profils `us.*` ou `global.*` :

```text
AccessDeniedException: openai.gpt-5.4 is not available for this account.
AccessDeniedException: openai.gpt-6-astra is not available for this account.
```

Ils nécessitent vraisemblablement une souscription Marketplace / un instrument de
paiement valide. Ce n'est pas un problème de code ni de région.

Sur le profil `default` (compte `990508469794`), quelques appels ont néanmoins réussi
(`us.openai.gpt-5.5`, `us.openai.gpt-6-sol` en `Converse` et `ConverseStream`), puis les
mêmes modèles ont renvoyé :

```text
AccessDeniedException: INVALID_PAYMENT_INSTRUMENT
```

L'accès est donc **intermittent et non fiable** : inutilisable pour un benchmark
reproductible. Le profil `meridian-bedrock` (compte `267949810690`) n'y a pas accès du
tout. Les modèles GPT propriétaires ne sont pas retenus.

### Modèles GPT-OSS (open-weight)

Les modèles **GPT-OSS** sont disponibles en `us-east-1`, en `ON_DEMAND` :

| Modèle | `Converse` | `ConverseStream` | Tool use |
|---|---|---|---|
| `openai.gpt-oss-120b-1:0` | ✅ | ✅ | ✅ streaming et non-streaming |
| `openai.gpt-oss-20b-1:0` | ✅ | ✅ | ✅ streaming et non-streaming |
| `openai.gpt-oss-safeguard-120b` | ✅ | ✅ | non testé |
| `openai.gpt-oss-safeguard-20b` | ✅ | ✅ | non testé |

Ils ne sont **pas disponibles en `ca-central-1`** : le catalogue canadien n'en contient
aucun. Les utiliser en `us-east-1` sort donc de la résidence canadienne.

À noter en `us-east-1` : les profils `ca.*` sont invalides, et les anciens
`anthropic.claude-3-sonnet`/`claude-3-haiku` sont en **fin de vie** (« This model version
has reached the end of its life »). Les modèles Bedrock réellement utilisables pour le
chat y sont donc Mistral Large, Llama 70B et GPT-OSS 120B/20B.

## Protocole

- 11 scénarios × 3 runs = **33 runs**.
- Flore : API Méridian réelle, `AWS_PROFILE=meridian-bedrock`,
  `BEDROCK_REGION=us-east-1`, chat `openai.gpt-oss-120b-1:0`.
- Baseline : le **même modèle**, appelé directement sans outils ni connaissances Méridian.
- Juge : `mistral.mistral-large-2402-v1:0`, à l'aveugle.
- Embeddings : Titan V2 en `us-east-1` pour l'API de test (1024 dimensions). La cible de
  production reste `ca-central-1` ; ce pilote mesure surtout le chat.

## Résultats

| Indicateur | Flore + Méridian (GPT-OSS 120B) | Assistant seul (GPT-OSS 120B) |
|---|---:|---:|
| Critères déterministes | **26/33 (79 %)** | 7/33 (21 %) |
| Pass@k | **100 %** | 27 % |
| Durée moyenne | 22,2 s | 6,9 s |
| Jugements | **22 victoires, 7 défaites, 4 égalités** | — |
| Taux de victoire | **67 %** (IC95 51–83 %) | — |

### Comparaison des modèles

| Modèle de Flore | Région | Déterministe | Pass@k | Juge |
|---|---|---:|---:|---:|
| DeepSeek | hors Canada | 30/33 (91 %) | 100 % | 28/33 (85 %) |
| **GPT-OSS 120B** | **us-east-1** | **26/33 (79 %)** | **100 %** | **22/33 (67 %)** |
| Nova Lite | `ca-central-1` | 13/33 (39 %) | 64 % | 23/33 (70 %) |

GPT-OSS 120B est **nettement meilleur que Nova Lite** sur les critères déterministes
(+40 points) et atteint 100 % de pass@k. Il reste sous DeepSeek (91 %), mais dans la même
famille de qualité.

Le taux de victoire au juge (67 %) est plus bas que Nova Lite (70 %) parce que le
**baseline est beaucoup plus fort** : GPT-OSS 120B seul répond déjà correctement à
certaines questions, ce qui rend la comparaison plus difficile. Ce n'est pas une baisse de
qualité de Flore.

### Points faibles restants

- `must_cite_evidence` manque encore dans quelques runs : GPT-OSS mobilise souvent les
  jumeaux et cite, mais pas systématiquement.
- `conduit-unknown-metric` : l'abstention n'est pas toujours reconnue.
- `conduit-compare` et `conduit-false-premise` : 3/3 aux critères déterministes mais
  0/3 au juge. Les réponses sont factuellement bonnes ; le juge préfère la formulation du
  baseline. C'est un désaccord de style/calibration, pas un échec de preuve.
- Le premier appel `mobiliser_jumeaux` a d'abord utilisé `mission` au lieu de `question`
  (`TypeError`), puis GPT-OSS a corrigé seul. Le docstring et le prompt ont été précisés
  depuis.

## Enseignements

- **Claude n'est pas indispensable** : GPT-OSS 120B est un modèle Bedrock réel, outillé,
  qui fait tourner Flore de bout en bout avec 79 % de critères déterministes.
- **Mais GPT-OSS n'est pas canadien** : il n'existe pas en `ca-central-1`. Pour le profil
  bancaire canadien, il ne remplace pas Claude/Mistral/Nova Lite.
- Les modèles GPT propriétaires (GPT-5/6) restent inaccessibles au compte ; il faudrait
  une souscription Marketplace ou un autre compte.
- GPT-OSS est un excellent **banc d'essai de qualité** pour le harness, hors résidence.

## Artefacts

```text
plugin/meridian/evals/conversations/pilots/2026-11-06-gptoss-us-east-1/REPORT.md
plugin/meridian/evals/conversations/pilots/2026-11-06-gptoss-us-east-1/summary.json
/tmp/opencode/conversations-gptoss-final/REPORT.md
/tmp/opencode/conversations-gptoss-final/summary.json
```

## Vérifications

```text
Accès GPT-OSS 120B/20B : Converse + ConverseStream + tool use OK
Benchmark : 26/33 déterministe, pass@k 100 %, 22/33 au juge
API health (us-east-1) : 200
```
