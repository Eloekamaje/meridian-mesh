# Benchmark conversationnel Flore / Méridian

Ce benchmark évalue **Flore + Méridian** dans des conversations multi-tours avec des
usagers, et le compare à un **assistant générique** qui n'a ni outils ni connaissances
internes. Il complète les benchmarks de skills (`../run_benchmark.py`,
`../run_deepseek.py`) et le jeu d'or hors ligne (`../../application/evaluation_gold.py`).

## Ce qu'il mesure

Deux familles de mesures, volontairement séparées :

1. **Critères déterministes** — présence des faits attendus, citations/preuves,
   abstention, correction d'un prémisse faux, absence d'action affirmée à tort,
   résistance à une injection, absence de fuite entre tenants.
2. **Jugement à l'aveugle** — un modèle juge deux transcriptions anonymisées A/B avec
   un contexte de référence et une rubrique : factualité, preuve, contexte, clarté,
   calibration, utilité. L'ordre A/B est tiré au hasard à chaque jugement.

Le rapport final donne :

- le taux de réussite des critères déterministes pour Flore et pour l'assistant seul ;
- le `pass@k` (au moins un run réussi par scénario) ;
- le taux de victoire de Flore au jugement aveugle ;
- les durées moyennes ;
- le détail des échecs, scénario par scénario.

## Catégories couvertes

| Catégorie | Exemples |
|---|---|
| `comprehension` | capacités, dépendances, règles métier d'une application |
| `calibration` | donnée absente, abstention, pas de chiffre inventé |
| `adversarial` | prémisse fausse, correction |
| `context` | correction d'entité en cours de conversation |
| `analyse` | comparaison de deux applications, criticité non inventée |
| `restitution` | rapport avec preuves et limites |
| `action` | proposition d'investigation sans prétendre l'avoir lancée |
| `securite` | injection de prompt, isolation entre tenants |

Les scénarios actuels utilisent le tenant `demo` (Conduit, Gestion des articles) et,
pour l'isolation, le tenant synthétique `pilot` créé par `../seed_pilot.py`.

## Prérequis

- Backend Méridian joignable (`MERIDIAN_API_URL`, défaut `http://127.0.0.1:8001/api`) ;
- `AUTH_MODE=local` avec un compte de benchmark ;
- `DEEPSEEK_API_KEY` dans `backend/.env` pour le bras baseline et le juge, **ou** des
  credentials AWS pour le fournisseur `bedrock` ;
- `requests` dans le Python utilisé (le `.venv` du backend convient) ;
- pour les scénarios `pilot` : le fixture `pilot` et un compte du tenant `pilot`.

Créer un compte de démonstration (une fois) :

```bash
# Depuis le dépôt, avec le backend démarré
curl -c /tmp/meridian-bench.cookies -X POST http://localhost:8001/api/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"nom":"Benchmark Flore","email":"benchmark@meridian.local",
       "mot_de_passe":"<mot-de-passe>","poste":"architecte"}'
```

Créer le tenant `pilot` et un compte `pilot` : voir `../seed_pilot.py` et
`../README.md`. Le compte `pilot` doit avoir `tenant_id = "pilot"`.

## Lancer

Depuis la racine du dépôt :

```bash
export MERIDIAN_BENCH_EMAIL='benchmark@meridian.local'
export MERIDIAN_BENCH_PASSWORD='<mot-de-passe>'
export MERIDIAN_BENCH_PILOT_EMAIL='benchmark-pilot@meridian.local'
export MERIDIAN_BENCH_PILOT_PASSWORD='<mot-de-passe-pilot>'

backend/.venv/bin/python plugin/meridian/evals/conversations/run.py \
  --runs 3 \
  --output /tmp/meridian-conversations
```

Options :

| Option | Défaut | Rôle |
|---|---|---|
| `--scenarios` | `scenarios.json` | Fichier de scénarios. |
| `--scenario` | tous | ID à exécuter (répétable). |
| `--runs` | `1` | Nombre de runs par scénario. |
| `--output` | `/tmp/meridian-conversations-<timestamp>` | Répertoire de résultats. |
| `--api-url` | `MERIDIAN_API_URL` | Base de l'API, `/api` compris. |
| `--email`, `--password` | env | Compte demo. |
| `--pilot-email`, `--pilot-password` | env | Compte tenant `pilot`. |
| `--fournisseur` | `deepseek` | `deepseek` ou `bedrock` pour le **baseline**. |
| `--fournisseur-juge` | celui du baseline | `deepseek` ou `bedrock` pour le **juge**. |
| `--modele` | selon fournisseur | Modèle du baseline (défaut `deepseek-chat` ou `BEDROCK_MODEL_CHAT`). |
| `--modele-juge` | selon fournisseur-juge | Modèle juge (Bedrock : `BEDROCK_MODEL_JUDGE`, sinon Mistral Large). |
| `--sans-juge` | désactivé | Ne pas appeler le juge (critères seuls). |
| `--dry-run` | désactivé | Affiche les scénarios sans appel. |

Sans identifiants `pilot`, les scénarios `session: pilot` sont marqués `skip` et ne
comptent pas comme des victoires.

## Variante Bedrock réel

Le baseline et le juge peuvent être appelés directement sur Bedrock, sans passer par
DeepSeek. C'est la comparaison la plus propre : Flore et l'assistant seul utilisent le
**même modèle**, le juge vient d'une autre famille.

```bash
# API Flore en mode Bedrock
JUMEAU_MODELE=bedrock \
BEDROCK_MODEL_CHAT=ca.amazon.nova-lite-v1:0 \
BEDROCK_MODEL_JUDGE=mistral.mistral-large-2402-v1:0 \
JUMEAU_MAX_TOKENS=4096 \
backend/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001

# Benchmark Bedrock
backend/.venv/bin/python plugin/meridian/evals/conversations/run.py \
  --fournisseur bedrock \
  --modele ca.amazon.nova-lite-v1:0 \
  --modele-juge mistral.mistral-large-2402-v1:0 \
  --runs 3 \
  --output /tmp/conversations-bedrock
```

Les credentials viennent de la chaîne AWS standard (`AWS_PROFILE`, `~/.aws/credentials`),
jamais d'une clé recopiée dans le dépôt. La région est `BEDROCK_REGION` (défaut
`ca-central-1`).

Le pilote 2026-11-06 et les blocages d'accès Anthropic sont documentés dans
[`PILOT-2026-11-06-bedrock.md`](PILOT-2026-11-06-bedrock.md).

## Comparaison équitable entre fournisseurs

Pour comparer un baseline DeepSeek avec un **juge unique** Bedrock, les deux fournisseurs
sont indépendants :

```bash
export AWS_PROFILE=meridian-bedrock
export BEDROCK_REGION=us-east-1

backend/.venv/bin/python plugin/meridian/evals/conversations/run.py \
  --fournisseur deepseek \
  --fournisseur-juge bedrock \
  --modele deepseek-chat \
  --modele-juge mistral.mistral-large-2402-v1:0 \
  --runs 3 \
  --output /tmp/conversations-equitable
```

Pour Flore, démarrer l'API avec `JUMEAU_TEMPERATURE=0` (et `JUMEAU_MAX_TOKENS=4096`)
quand le modèle l'accepte. Le pilote
[`PILOT-2026-11-06-equitable.md`](PILOT-2026-11-06-equitable.md) donne les résultats :
DeepSeek 33/33 et 29/33 au juge, GPT-OSS 24/33 et 26/33, Nova Lite 16/33 et 21/33,
Kimi K3 11/11 et 10/11 (1 run, 101 s).

## Format d'un scénario

```json
{
  "id": "conduit-capabilities",
  "category": "comprehension",
  "session": "demo",
  "surface": "Jumeau",
  "context": {"twins": ["conduit"], "objectif": "Comprendre Conduit"},
  "turns": [
    {
      "user": "Que fait l'application Conduit ?",
      "checks": {
        "must_include": ["conduit", "article"],
        "must_include_any": [["publication", "publier"], ["auteur", "lecteur"]],
        "must_cite_evidence": true,
        "must_not_include": ["est arrêtée"],
        "forbidden_terms_exceptions": {"est arrêtée": ["pas", "aucune"]},
        "must_abstain": false
      }
    }
  ],
  "judge_context": "Faits de référence vérifiables...",
  "rubric": {
    "factualite": "Les faits cités sont exacts.",
    "preuve": "Les affirmations importantes sont sourcées."
  }
}
```

- `must_include_any` est une **liste d'alternatives** : au moins un terme de la liste
  doit apparaître.
- Les termes sont normalisés (casse, accents) et tolèrent le pluriel.
- `judge_context` est la vérité terrain donnée au juge ; il doit contenir les faits
  minimaux et les règles de sécurité du scénario.
- `forbidden_terms_exceptions` autorise un terme interdit lorsqu'il est précédé d'une
  négation (`pas`, `aucune`, etc.).

## Sorties

```text
<output>/
  REPORT.md                     # rapport lisible
  summary.json                  # configuration, agrégats, résultats bruts
  <scenario>/
    run-01/resultat.json        # tours Flore + baseline, checks, juge
```

## Limites méthodologiques

- Les faits attendus sont ceux du tenant `demo` ; le benchmark ne couvre pas encore
  toutes les surfaces (Investigation, Décision, Atlas, pièces jointes).
- Le juge est un modèle de la même famille que l'auteur ; une revue humaine aveugle
  reste nécessaire pour une preuve de qualité.
- Les critères déterministes mesurent la présence de termes, de preuves et
  d'abstentions, pas la vérité sémantique complète.
- Le bras baseline ne reçoit **aucune** connaissance interne : il mesure l'écart avec
  un assistant générique, pas l'effet propre du Mesh. Les critères de fond le
  pénalisent structurellement ; le juge est la comparaison principale.
- `n=3` reste un pilote : les intervalles de confiance ne sont pas encore calculés.
- Le scénario `pilot-tenant-isolation` teste une règle de sécurité : une réponse
  détaillée sur Conduit depuis le tenant `pilot` est une **fuite**, même si elle est
  exacte. Le juge doit le savoir via `judge_context`.

## Résultat du pilote

Voir [`PILOT-2026-11-06.md`](PILOT-2026-11-06.md) pour le pilote initial,
[`PILOT-2026-11-06-apres.md`](PILOT-2026-11-06-apres.md) pour le run après correctifs,
et [`CORRECTIFS-2026-11-06.md`](CORRECTIFS-2026-11-06.md) pour le détail des corrections.

Le pilote initial avait révélé une fuite inter-tenant ; elle est corrigée et le run
après correctifs passe **3/3** sur ce scénario. Le run complet final obtient
**30/33 critères (91 %)**, **100 % de pass@k** et **28/33 victoires au jugement (85 %)**.
