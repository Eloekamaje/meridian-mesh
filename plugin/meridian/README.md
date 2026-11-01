# Plugin Méridian

Plugin portable pour Claude Code, Codex, OpenCode et tout harness supportant **skills**, **subagents** et **MCP**.

Il ne remplace pas le backend Méridian : il l'expose proprement.

## Contenu

- 4 **skills** : `incident-ops`, `architecture-impact`, `benefits-okr`, `enterprise-portfolio`.
- 3 **subagents** : `verificateur`, `analyste-impact`, `decouvreur`.
- 1 **serveur MCP read-only** : profils, composition, analyse globale/applicative, portefeuille, Value Ledger, impact, Claims, learnings, attention, contexte, mémoire durable, consolidation, calibration, contrefactuel.
- 1 **policy** d'autorité : lecture/proposition, écritures interdites sans approbation humaine.
- 1 **contrat de réponse** : socle de faits invariant + lentille de profil.
- 3 **profils pilotes** : ops, architecte, product_owner.
- 2 **domain packs** : `paiements` et `risque`, qui activent des méthodes/compétences existantes, portent 4 questions d'évaluation avec preuves attendues et restent en lecture seule (`domain-packs/*.json`).
- 1 **jeu d'or hors ligne** outils/Claims/décisions : `evals/gold/outils-claims-decisions.json`, exécutable sans modèle ni réseau via `backend/jumeau/evaluation_gold.py`.

## Domain packs

Les packs sont des descripteurs JSON, pas un framework parallèle : ils référencent uniquement les méthodes et compétences des catalogues (`methodes_cognitives`, `competences_cognitives`) et déclarent un périmètre, 3 à 5 questions d'évaluation avec preuves attendues/clés de réponse, et une autorité lecture seule.

Le chargeur/validateur est `backend/jumeau/packs_domaines.py` (`charger_packs`, `valider_pack`). La composition accepte un pack explicite :

```python
from jumeau import composition
plan = composition.planifier("ops", "incident de paiement", pack="paiements")
```

Un pack inconnu, une méthode/compétence hors catalogue, une autorité d'écriture ou un nombre d'évaluations hors borne sont refusés.

## Prérequis

- backend Méridian lancé (`MERIDIAN_API_URL`, défaut `http://127.0.0.1:8001/api`) ;
- Python avec le paquet `mcp` et `requests` ;
- variables `MERIDIAN_TENANT` et `MERIDIAN_PERSONA`.

## Claude Code

Installation projet reproductible (sans configuration globale) :
[`docs/plugin/INSTALL.md`](../../docs/plugin/INSTALL.md).

Installer le marketplace local :

```bash
/plugin marketplace add "$PWD/plugin/meridian"
/plugin install meridian@meridian
```

Ou copier/lier les skills et agents manuellement :

```bash
mkdir -p ~/.claude/skills ~/.claude/agents
ln -sfn "$PWD/plugin/meridian/skills/incident-ops" ~/.claude/skills/meridian-incident-ops
ln -sfn "$PWD/plugin/meridian/skills/architecture-impact" ~/.claude/skills/meridian-architecture-impact
ln -sfn "$PWD/plugin/meridian/skills/benefits-okr" ~/.claude/skills/meridian-benefits-okr
cp plugin/meridian/agents/*.md ~/.claude/agents/
```

Déclarer le MCP :

```bash
claude mcp add meridian \
  --env MERIDIAN_API_URL=http://127.0.0.1:8001/api \
  --env MERIDIAN_TENANT=demo \
  --env MERIDIAN_PERSONA=architecte \
  -- python -m plugin.meridian.mcp.server
```

Le MCP doit être lancé depuis la racine du dépôt, ou avec `PYTHONPATH` pointant vers elle.

## Codex

Ajouter les instructions du plugin dans `AGENTS.md`, puis déclarer le serveur MCP :

```toml
[mcp_servers.meridian]
command = "python"
args = ["-m", "plugin.meridian.mcp.server"]
env = { MERIDIAN_API_URL = "http://127.0.0.1:8001/api", MERIDIAN_TENANT = "demo", MERIDIAN_PERSONA = "architecte" }
```

Codex utilise les skills si sa version les supporte ; sinon, les fichiers `skills/*/SKILL.md` servent de playbooks et les agents de prompts de subagents.

## OpenCode

Dans `opencode.json` :

```json
{
  "skills": { "paths": ["./plugin/meridian/skills"] },
  "mcp": {
    "meridian": {
      "type": "local",
      "command": ["python", "-m", "plugin.meridian.mcp.server"],
      "environment": {
        "MERIDIAN_API_URL": "http://127.0.0.1:8001/api",
        "MERIDIAN_TENANT": "demo",
        "MERIDIAN_PERSONA": "architecte"
      }
    }
  }
}
```

Les agents `agents/*.md` peuvent être copiés dans `.opencode/agents/` ou convertis dans la section `agent` de la configuration.

Chaque skill suit la divulgation progressive : `SKILL.md` court, `references/` pour les contrats et `evals/` pour les cas de test. Les skills passent le validateur Agent Skills et sont packageables avec `skill-creator/scripts/package_skill.py`.

Le benchmark et la décision de pilote sont documentés dans [`evals/BENCHMARK.md`](evals/BENCHMARK.md), [`evals/PILOT-REVIEW.md`](evals/PILOT-REVIEW.md) et [`evals/PILOT-2026-11-01.md`](evals/PILOT-2026-11-01.md). Les runs réels du pilote utilisent [`evals/run_deepseek.py`](evals/run_deepseek.py) sur le backend `JUMEAU_MODELE=deepseek` ; **Claude Code n'a pas été appelé**. Le harness Claude reste disponible comme artefact historique. Décision : no-go production, go conditionnel pour une seconde itération avec revue humaine et outcome réel.

## Utilisation

Une skill choisit une posture et une méthode, puis appelle `meridian_analyser`.

Exemple :

```text
Analyse l'incident de latence paiements avec la skill meridian-incident-ops.
Utilise le profil ops, la situation sit-latence-paiements et les Twins paiements/comptes.
```

Pour une question globale : utiliser `meridian_portefeuille` ou `meridian_analyser` sans application ; le résultat contient `valeur` (situations, situations hautes, décisions, initiatives, outcomes, learnings).

Le Value Ledger est accessible par `meridian_valeurs` et `meridian_valeur_resume` ; il ne mélange jamais devises et unités.

Outils de contexte et de mémoire, tous en lecture seule :

- `meridian_contexte` résout explicitement une surface et ses entités, sans laisser le modèle deviner un id ;
- `meridian_memoire_durable` liste ou recherche la mémoire durable, sans création ni suppression ;
- `meridian_memoire_consolidation` propose doublons et conflits, sans id ni acteur : aucune approbation, aucune écriture ;
- `meridian_calibration` lit le rapport de calibration global ou par décision ;
- `meridian_contrefactuel` compare des options sans prétention causale.

Le résultat contient :

- `socle.faits` : faits, preuves, incertitudes, limites, **identiques pour tous les profils** ;
- `lecture` : sections adaptées au profil ;
- `actions` : propositions, jamais exécutées ;
- `autorite` : jamais au-delà de `proposition` ;
- `prochaines_etapes`.

## Règles non négociables

- le plugin ne fait aucune écriture canonique ;
- le tenant et le périmètre viennent de l'identité, pas du texte utilisateur ;
- un profil inconnu reste en lecture seule ;
- un model ne décide ni ne promeut ;
- une méthode absente du catalogue n'est pas inventée ;
- une preuve absente n'est pas une preuve d'absence.
