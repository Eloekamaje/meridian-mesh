# Plugin Méridian

Plugin portable pour Claude Code, Codex, OpenCode et tout harness supportant **skills**, **subagents** et **MCP**.

Il ne remplace pas le backend Méridian : il l'expose proprement.

## Contenu

- 4 **skills** : `incident-ops`, `architecture-impact`, `benefits-okr`, `enterprise-portfolio`.
- 3 **subagents** : `verificateur`, `analyste-impact`, `decouvreur`.
- 1 **serveur MCP read-only** : profils, composition, analyse globale/applicative, portefeuille, Value Ledger, impact, Claims, learnings, attention.
- 1 **policy** d'autorité : lecture/proposition, écritures interdites sans approbation humaine.
- 1 **contrat de réponse** : socle de faits invariant + lentille de profil.
- 3 **profils pilotes** : ops, architecte, product_owner.

Les domain packs sont volontairement absents.

## Prérequis

- backend Méridian lancé (`MERIDIAN_API_URL`, défaut `http://127.0.0.1:8001/api`) ;
- Python avec le paquet `mcp` et `requests` ;
- variables `MERIDIAN_TENANT` et `MERIDIAN_PERSONA`.

## Claude Code

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

Le benchmark local avec/sans skill est documenté dans [`evals/BENCHMARK.md`](evals/BENCHMARK.md). Il montre un gain de discipline et de temps sur un incident, mais reste un signal à répéter.

## Utilisation

Une skill choisit une posture et une méthode, puis appelle `meridian_analyser`.

Exemple :

```text
Analyse l'incident de latence paiements avec la skill meridian-incident-ops.
Utilise le profil ops, la situation sit-latence-paiements et les Twins paiements/comptes.
```

Pour une question globale : utiliser `meridian_portefeuille` ou `meridian_analyser` sans application ; le résultat contient `valeur` (situations, situations hautes, décisions, initiatives, outcomes, learnings).

Le Value Ledger est accessible par `meridian_valeurs` et `meridian_valeur_resume` ; il ne mélange jamais devises et unités.

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
