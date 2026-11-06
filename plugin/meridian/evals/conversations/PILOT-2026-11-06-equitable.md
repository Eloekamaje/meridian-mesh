# Comparaison équitable — 2026-11-06

## Question

Les pilotes précédents n’étaient pas directement comparables : DeepSeek était jugé par
DeepSeek, les modèles Bedrock par Mistral Large, et le nombre de runs variait. Peut-on
comparer les modèles **à protocole égal** ?

## Protocole corrigé

- **Mêmes 11 scénarios**, mêmes textes, mêmes critères déterministes.
- **Juge unique** : `mistral.mistral-large-2402-v1:0`, en `us-east-1`, à l’aveugle, pour
  les quatre modèles. Ce n’est ni DeepSeek, ni GPT-OSS, ni Nova Lite, ni Kimi.
- **Baseline** : le même modèle que Flore, appelé directement sans outils ni
  connaissances Méridian.
- **Température** : 0 pour DeepSeek, GPT-OSS et Nova Lite. Kimi K3 refuse le champ
  `temperature` ; il tourne avec son défaut, ce qui est une limite du modèle.
- **Runs** : 3×11 pour DeepSeek, GPT-OSS et Nova Lite ; 1×11 pour Kimi K3, dont la
  latence rend 3 runs très coûteux (environ 55 minutes).
- **Même code, mêmes prompts, mêmes outils** pour tous les modèles.
- **Régions** : DeepSeek est externe ; les modèles Bedrock sont en `us-east-1`. Ce n’est
  donc pas une comparaison de résidence canadienne, mais de qualité du harness à
  protocole égal.

## Résultats

| Modèle | Région | Runs | Déterministe | Pass@k | Juge (V/D/E) | Taux de victoire | Durée moy. |
|---|---|---:|---:|---:|---|---:|---:|
| **DeepSeek** | externe | 3×11 | **33/33 (100 %)** | 100 % | 29/0/4 | 88 % (IC95 77–99 %) | 45,2 s |
| **GPT-OSS 120B** | `us-east-1` | 3×11 | **24/33 (73 %)** | 82 % | 26/4/3 | 79 % (IC95 65–93 %) | 23,2 s |
| **Nova Lite** | `us-east-1` | 3×11 | **16/33 (48 %)** | 64 % | 21/4/8 | 64 % (IC95 47–80 %) | 26,5 s |
| **Kimi K3** | `us-east-1` | 1×11 | **11/11 (100 %)** | 100 % | 10/0/1 | 91 % (IC95 74–100 %) | 101,1 s |

### Lecture

- **DeepSeek** est le meilleur modèle **robuste sur 3 runs** : 33/33 aux critères
  déterministes, 29/33 au juge (88 %), 45 s de moyenne.
- **Kimi K3** est au même niveau, voire au-dessus sur ce run : 11/11 et 10/11 au juge
  (91 %). Mais il n’a qu’un run, refuse la température imposée, et met **101 s** en
  moyenne, avec des pointes à plusieurs minutes. Ce n’est pas un modèle de chat temps
  réel.
- **GPT-OSS 120B** est le meilleur compromis rapide hors Canada : 24/33 (73 %) et
  26/33 au juge (79 %), en 23 s. Il est loin derrière DeepSeek/Kimi sur les critères
  déterministes, surtout à cause des citations manquantes.
- **Nova Lite** reste insuffisant : 16/33 (48 %) et 21/33 au juge (64 %).

### Échecs déterministes

- **DeepSeek** : aucun.
- **GPT-OSS 120B** : citations manquantes (`conduit-capabilities`, `conduit-false-premise`),
  FastAPI/uvicorn absents (`conduit-dependencies`), abstention non reconnue
  (`conduit-unknown-metric`).
- **Nova Lite** : citations, règles métier, dépendances, comparaison, prémisse fausse,
  rapport.
- **Kimi K3** : aucun.

## Ce que cette comparaison corrige

- Un **juge unique** (Mistral Large) pour tous les modèles, au lieu du juge DeepSeek du
  pilote initial.
- Le **même nombre de runs** pour les trois modèles principaux.
- La **même température** (0) pour les modèles qui l’acceptent.
- Les **mêmes scénarios, prompts, outils et code**.

Le **33/33 de DeepSeek** n’est pas le 30/33 du pilote précédent : cette campagne ajoute
la température 0, le plafond de 4096 tokens et les correctifs de prompt/outil
(`mobiliser_jumeaux`, consigne de tool use natif). Ce n’est donc pas le même run.

## Ce qu’elle ne corrige pas

- Kimi K3 n’a qu’un run et ne supporte pas la température : sa ligne n’est pas strictement
  comparable aux trois autres.
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

## Conclusion

À protocole égal, **DeepSeek reste la référence robuste** (100 % déterministe sur 3 runs,
88 % au juge). **Kimi K3** atteint le même niveau de qualité mais reste trop lent pour un
chat temps réel. **GPT-OSS 120B** est le meilleur compromis rapide hors Canada, et
**Nova Lite** ne suffit pas pour le contrat outil/preuve de Flore.

Pour le profil bancaire canadien, cette comparaison ne tranche pas : DeepSeek, GPT-OSS et
Kimi sont hors résidence ; Claude reste bloqué par le formulaire/paiement ; Mistral Large
demande encore l’adaptation de son tool use non-streaming ; Nova Lite est le seul modèle
canadien qui fonctionne, mais à 48 % de critères déterministes.

## Artefacts

```text
plugin/meridian/evals/conversations/pilots/2026-11-06-equitable/REPORT.md
plugin/meridian/evals/conversations/pilots/2026-11-06-equitable/summary.json
/tmp/opencode/fair-2026-11-06/REPORT.md
/tmp/opencode/fair-2026-11-06/deepseek/REPORT.md
/tmp/opencode/fair-2026-11-06/gptoss/REPORT.md
/tmp/opencode/fair-2026-11-06/nova-lite/REPORT.md
/tmp/opencode/fair-2026-11-06/kimi2/REPORT.md
```

## Vérifications

```text
Juge unique Mistral Large : oui
DeepSeek : 33/33 déterministe, 29/33 juge
GPT-OSS  : 24/33 déterministe, 26/33 juge
Nova Lite: 16/33 déterministe, 21/33 juge
Kimi K3  : 11/11 déterministe, 10/11 juge (1 run)
Tests plugin : 62 passed
```
