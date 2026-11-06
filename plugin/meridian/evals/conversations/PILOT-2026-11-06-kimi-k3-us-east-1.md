# Pilote Kimi K3 — 2026-11-06

> **Comparaison équitable** : le pilote [`PILOT-2026-11-06-equitable.md`](PILOT-2026-11-06-equitable.md)
> reprend Kimi K3 après le correctif « température non supportée » : **11/11 (100 %)** aux
> critères déterministes et **10/11 (91 %)** au juge, en **101 s** de moyenne, sur 1 run.
> Le présent document conserve le premier run (9/11, 87 s), antérieur à ce correctif.

## Question

Kimi K3 est-il une alternative crédible à Claude/GPT-OSS sur Bedrock, et que vaut Flore
avec lui ?

## Accès réel

Kimi K3 (`moonshotai.kimi-k3`) est au catalogue, mais **uniquement via des profils
d'inférence** `us.moonshotai.kimi-k3` ou `global.moonshotai.kimi-k3`. L'appel direct
`moonshotai.kimi-k3` en on-demand est refusé.

| Élément | Constat |
|---|---|
| `us.moonshotai.kimi-k3` | ✅ `Converse` + `ConverseStream` |
| `global.moonshotai.kimi-k3` | ✅ `Converse` + `ConverseStream` |
| Tool use | ✅ streaming et non-streaming |
| Strands | ✅ streaming et non-streaming |
| Profil canadien `ca.*` | ❌ inexistant |
| Résidence | ❌ `us.`/`global.` routent hors Canada |

Kimi K3 fonctionne depuis l'endpoint `ca-central-1` **si on utilise un profil `us.` ou
`global.`**, mais l'inférence est alors routée hors Canada. Ce n'est donc pas un modèle
canadien, même si l'appel part de `ca-central-1`.

## Protocole

- 11 scénarios × 1 run = **11 runs**.
- Flore : API Méridian réelle, `AWS_PROFILE=meridian-bedrock`,
  `BEDROCK_REGION=us-east-1`, chat `us.moonshotai.kimi-k3`.
- Baseline : le **même modèle**, appelé directement sans outils ni connaissances Méridian.
- Juge : `mistral.mistral-large-2402-v1:0`, à l'aveugle.
- Embeddings : Titan V2 en `us-east-1` (1024 dimensions).

Un run préparatoire ciblé sur 5 scénarios clés avait donné 4/5 aux critères déterministes
et 4 victoires / 0 défaite / 1 égalité au juge.

## Résultats

| Indicateur | Flore + Méridian (Kimi K3) | Assistant seul (Kimi K3) |
|---|---:|---:|
| Critères déterministes | **9/11 (82 %)** | 3/11 (27 %) |
| Pass@k | **82 %** | 27 % |
| Durée moyenne | **87,4 s** | 5,5 s |
| Jugements | **8 victoires, 1 défaite, 2 égalités** | — |
| Taux de victoire | **73 %** (IC95 46–99 %) | — |

### Comparaison

| Modèle de Flore | Région | Runs | Déterministe | Juge | Durée moy. |
|---|---|---:|---:|---:|---:|
| DeepSeek | hors Canada | 3×11 | 30/33 (91 %) | 28/33 (85 %) | ~? |
| Kimi K3 | `us.`/`global.` | 1×11 | **9/11 (82 %)** | **8/11 (73 %)** | **87,4 s** |
| GPT-OSS 120B | `us-east-1` | 3×11 | 26/33 (79 %) | 22/33 (67 %) | 22,2 s |
| Nova Lite | `ca-central-1` | 3×11 | 13/33 (39 %) | 23/33 (70 %) | 10,9 s |

Kimi K3 est **qualitativement au niveau de GPT-OSS 120B**, avec un point estimé
légèrement supérieur (82 % contre 79 % sur des protocoles différents : 1 run contre 3).
Il produit des réponses riches, bien structurées et citées.

### Le problème : la latence

Kimi K3 est **très lent** :

- 87,4 s en moyenne par scénario, contre 22,2 s pour GPT-OSS et 10,9 s pour Nova Lite ;
- certains scénarios dépassent 2 à 3 minutes :
  - `conduit-compare` : 211 s ;
  - `conduit-report` : 179 s ;
  - `conduit-investigation` : 136 s.

Un benchmark 3 runs prendrait environ **45–60 minutes**. Pour une conversation
interactive, ce n'est pas acceptable sans un budget de latence important.

### Échecs

- `conduit-report` : le format de rapport attendu (`preuve`, `synthèse`, `limites`) n'est
  pas reconnu, et aucune preuve n'est citée.
- `conduit-unknown-metric` : l'abstention n'est pas reconnue, comme avec plusieurs autres
  modèles.
- Les 9 autres scénarios passent, y compris les règles métier, les dépendances, la
  comparaison, la correction de contexte, la prémisse fausse, l'investigation, la sécurité
  et l'isolation tenant.

## Enseignements

- **Kimi K3 est une vraie alternative qualité** : 82 % de critères déterministes, 73 % au
  juge, tool use complet, citations.
- **Il n'est pas canadien** : pas de profil `ca.*` ; `us.`/`global.` routent hors Canada.
- **Il est trop lent pour Flore en interaction** : 87 s en moyenne, jusqu'à 3,5 min.
- Il peut convenir à des usages **batch/analyse** ou à un benchmark hors ligne, pas à un
  chat temps réel.
- Comme GPT-OSS, il sert de **banc d'essai qualité** du harness, hors résidence.

## Artefacts

```text
plugin/meridian/evals/conversations/pilots/2026-11-06-kimi-k3-us-east-1/REPORT.md
plugin/meridian/evals/conversations/pilots/2026-11-06-kimi-k3-us-east-1/summary.json
/tmp/opencode/conversations-kimi-full1/REPORT.md
/tmp/opencode/conversations-kimi-full1/summary.json
```

## Vérifications

```text
Kimi K3 : Converse + ConverseStream + tool use OK via us./global.
Benchmark 1×11 : 9/11 déterministe, 8/11 au juge, 87,4 s de moyenne
API health (us-east-1) : 200
```
