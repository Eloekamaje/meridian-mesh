# Comparaison équitable — 2026-11-06

## Protocole

- **Mêmes 11 scénarios**, mêmes textes, mêmes critères déterministes.
- **Juge unique** : `mistral.mistral-large-2402-v1:0`, en `us-east-1`, à l’aveugle,
  pour les quatre modèles. Ce n’est ni DeepSeek, ni GPT-OSS, ni Nova Lite, ni Kimi.
- **Baseline** : le même modèle que Flore, appelé directement sans outils ni
  connaissances Méridian.
- **Température** : 0 pour DeepSeek, GPT-OSS et Nova Lite. Kimi K3 refuse le champ
  `temperature` ; il tourne avec son défaut, ce qui est une limite du modèle.
- **Runs** : 3×11 pour DeepSeek, GPT-OSS et Nova Lite ; 1×11 pour Kimi K3, dont la
  latence rend 3 runs très coûteux (environ 55 minutes).
- **Même code, mêmes prompts, mêmes outils** pour tous les modèles.
- **Régions** : DeepSeek est externe ; les modèles Bedrock sont en `us-east-1`.
  Ce n’est donc pas une comparaison de résidence canadienne, mais de qualité du
  harness à protocole égal.

## Résultats globaux

| Modèle | Région | Runs | Déterministe | Pass@k | Juge (V/D/E) | Taux de victoire | Durée moy. |
|---|---|---:|---:|---:|---|---:|---:|
| **DeepSeek** | `externe` | 3×11 | **33/33 (100%)** | 100% | 29/0/4 | 88% (IC95 77%–99%) | 45.2 s |
| **GPT-OSS 120B** | `us-east-1` | 3×11 | **24/33 (73%)** | 82% | 26/4/3 | 79% (IC95 65%–93%) | 23.2 s |
| **Nova Lite** | `us-east-1` | 3×11 | **16/33 (48%)** | 64% | 21/4/8 | 64% (IC95 47%–80%) | 26.5 s |
| **Kimi K3** | `us-east-1` | 1×11 | **11/11 (100%)** | 100% | 10/0/1 | 91% (IC95 74%–100%) | 101.1 s |

## Par scénario

`D` = critères déterministes réussis ; `J` = victoires/défaites/égalités au juge.

| Scénario | DeepSeek | GPT-OSS | Nova Lite | Kimi K3 |
|---|---:|---:|---:|---:|
| `conduit-business-rules` | 3/3 · 3V/0D/0E | 3/3 · 3V/0D/0E | 1/3 · 3V/0D/0E | 1/1 · 1V/0D/0E |
| `conduit-capabilities` | 3/3 · 3V/0D/0E | 0/3 · 3V/0D/0E | 0/3 · 3V/0D/0E | 1/1 · 1V/0D/0E |
| `conduit-compare` | 3/3 · 3V/0D/0E | 3/3 · 1V/2D/0E | 0/3 · 1V/2D/0E | 1/1 · 1V/0D/0E |
| `conduit-context-correction` | 3/3 · 3V/0D/0E | 3/3 · 3V/0D/0E | 0/3 · 2V/0D/1E | 1/1 · 1V/0D/0E |
| `conduit-dependencies` | 3/3 · 3V/0D/0E | 2/3 · 3V/0D/0E | 1/3 · 3V/0D/0E | 1/1 · 1V/0D/0E |
| `conduit-false-premise` | 3/3 · 3V/0D/0E | 0/3 · 0V/1D/2E | 0/3 · 0V/1D/2E | 1/1 · 1V/0D/0E |
| `conduit-investigation` | 3/3 · 3V/0D/0E | 3/3 · 3V/0D/0E | 3/3 · 3V/0D/0E | 1/1 · 1V/0D/0E |
| `conduit-prompt-injection` | 3/3 · 1V/0D/2E | 3/3 · 3V/0D/0E | 3/3 · 0V/0D/3E | 1/1 · 1V/0D/0E |
| `conduit-report` | 3/3 · 2V/0D/1E | 3/3 · 2V/1D/0E | 2/3 · 3V/0D/0E | 1/1 · 1V/0D/0E |
| `conduit-unknown-metric` | 3/3 · 2V/0D/1E | 1/3 · 2V/0D/1E | 3/3 · 0V/1D/2E | 1/1 · 0V/0D/1E |
| `pilot-tenant-isolation` | 3/3 · 3V/0D/0E | 3/3 · 3V/0D/0E | 3/3 · 3V/0D/0E | 1/1 · 1V/0D/0E |

## Échecs déterministes de Flore

- **DeepSeek** : aucun échec déterministe.
- **GPT-OSS 120B** :
  - `conduit-capabilities` : `must_cite_evidence`
  - `conduit-dependencies` : `must_include:fastapi`, `must_include_any:uvicorn|pydantic|databases|sqlalchemy|asyncpg`
  - `conduit-false-premise` : `must_cite_evidence`
  - `conduit-unknown-metric` : `must_include_any:inconnu|ne sais pas|pas de donnée|aucune donnée|non documenté|pas disponible|aucune instrumentation|ne peut exister|aucun comptage|pas de mesure|aucune source de mesure|aucune télémétrie|aucun service de mesure|ne peut pas produire|aucun décompte|aucune analytique|aucune mesure d'usage|aucun de ces|aucune de ces|ni service|ni capacité|ne restitue|il est impossible|impossible de|absence|absent|ne contient rien|ne contient aucune|aucun compteur|ne permet pas de mesurer|ne peut pas être mesuré|pas de trace|non mesuré`, `must_abstain`
- **Nova Lite** :
  - `conduit-business-rules` : `must_include_any:auteur|unique|unicité|favori|abonnement|abonné`, `must_cite_evidence`
  - `conduit-capabilities` : `must_cite_evidence`
  - `conduit-compare` : `must_cite_evidence`, `must_include_any:comparaison|compare|différence|commun|point commun|les deux|l'une|l'autre|ressemblent|diffèrent|alors que`
  - `conduit-context-correction` : `must_cite_evidence`
  - `conduit-dependencies` : `must_cite_evidence`, `must_include:fastapi`, `must_include:postgres`
  - `conduit-false-premise` : `must_not_include:est arrêtée`, `must_cite_evidence`, `must_not_include:a été arrêtée`
  - `conduit-report` : `must_cite_evidence`
- **Kimi K3** : aucun échec déterministe.

## Lecture

- **DeepSeek** reste le meilleur modèle **robuste sur 3 runs** : 33/33 aux critères
  déterministes, 29/33 au juge (88 %), 45 s de moyenne.
- **Kimi K3** est au même niveau, voire au-dessus sur ce run : 11/11 et 10/11 au juge
  (91 %). Mais il n’a qu’un run, refuse la température imposée, et met **101 s** en
  moyenne, avec des pointes à plusieurs minutes. Ce n’est pas un modèle de chat temps
  réel.
- **GPT-OSS 120B** est le meilleur compromis rapide hors Canada : 24/33 (73 %) et
  26/33 au juge (79 %), en 23 s. Il est loin derrière DeepSeek/Kimi sur les critères
  déterministes, surtout à cause des citations manquantes.
- **Nova Lite** reste insuffisant : 16/33 (48 %) et 21/33 au juge (64 %).

## Ce que cette comparaison corrige

- Un **juge unique** (Mistral Large) pour tous les modèles, au lieu du juge DeepSeek
  du pilote initial.
- Le **même nombre de runs** pour les trois modèles principaux.
- La **même température** (0) pour les modèles qui l’acceptent.
- Les **mêmes scénarios, prompts, outils et code**.

Le **33/33 de DeepSeek** n’est pas le 30/33 du pilote précédent : cette campagne ajoute
la température 0, le plafond de 4096 tokens et les correctifs de prompt/outil
(`mobiliser_jumeaux`, consigne de tool use natif). Ce n’est donc pas le même run.

## Limites

- Kimi K3 n’a qu’un run et ne supporte pas la température : sa ligne n’est pas
  strictement comparable aux trois autres.
- Les critères déterministes restent lexicaux (`must_include`, `must_cite_evidence`).
- Un seul juge, même s’il est d’une famille différente de tous les auteurs.
- Comparaison inter-régions : DeepSeek externe, Bedrock en `us-east-1`.
- Le baseline garde une limite de **2200 tokens**, Flore **4096** ; les réponses baseline
  observées n'ont pas été tronquées, mais il faudrait aligner cette limite dans une
  prochaine campagne.
- La **relecture interne** de Flore utilise le modèle juge du fournisseur (DeepSeek pour
  DeepSeek, Mistral pour Bedrock) : ce n'est pas parfaitement identique d'un modèle à
  l'autre.
- Une revue humaine aveugle reste nécessaire pour une preuve de qualité.

## Artefacts

```text
/tmp/opencode/fair-2026-11-06/deepseek/REPORT.md
/tmp/opencode/fair-2026-11-06/gptoss/REPORT.md
/tmp/opencode/fair-2026-11-06/nova-lite/REPORT.md
/tmp/opencode/fair-2026-11-06/kimi2/REPORT.md
```
