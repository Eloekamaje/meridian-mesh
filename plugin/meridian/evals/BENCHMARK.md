# Smoke test skills Méridian — 2026-10-30

## But

Comparer une exécution **avec skill** et **sans skill** sur deux workflows bancaires, avec le même MCP
Méridian read-only et le même modèle. Ce benchmark est un **smoke test**, pas une preuve statistique ni une preuve de valeur business. Il ne mesure pas l'effet Méridian sans MCP, ni la qualité décisionnelle contre un analyste humain.

## Protocole

- Harness : Claude Code 2.1.314, `claude -p`, MCP Méridian local.
- Modèle : `deepseek-flash` (session).
- Budget : 0,75 USD par run, timeout 150 s.
- Avec skill : projet contenant `.claude/skills/meridian-*`.
- Sans skill : répertoire vide, même MCP, même prompt.
- Une exécution par condition ; aucune moyenne, aucun test statistique.

## Workflow 1 — incident Paiements

Prompt : incident depuis 14 h, SLA menacé, contexte `sit-latence-paiements`, Twins `paiements`/`comptes`,
application `conduit`.

| Bras | Résultat | Durée | Coût | Outils |
|---|---|---:|---:|---|
| `skill+mcp` | **Passe** | 93 s | 0,66 USD | Skill + 5 outils MCP |
| `checklist+mcp` | **Échoue** : `prochaines_etapes` absentes | 161 s | 1,06 USD | 9 outils MCP, aucun Skill |
| `data-only` | **Passe** | 125 s | 0,72 USD | aucun outil, pack gelé |
| `human` | non exécuté | — | — | schéma de revue fourni |

## Workflow 2 — portefeuille Paiement

Prompt : concentration de valeur et de risque dans le domaine Paiement, avec Value Ledger.

| Condition | Résultat | Tours | Durée | Coût | Outils |
|---|---|---:|---:|---:|---|
| Avec `enterprise-portfolio` | Réponse complète, Value Ledger, limites, aucune causalité affirmée | 10 | 70 s | 0,58 USD | 2 outils (portefeuille + valeur) |
| Sans skill | Réponse complète mais plus longue, commence par « chaîne causale » puis la corrige | 16 | 143 s | 0,64 USD | 5 outils |

## Lecture

Ce dispositif ne permet pas d'affirmer que Méridian améliore les décisions : n=1, données demo, pas de revue humaine. Il permet de dire que la skill passe les critères de structure et réduit le coût/temps face à une checklist, pas qu'elle produit une meilleure décision business.

- Sur l'incident, `skill+mcp` est le seul bras rapide et complet ; `checklist+mcp` coûte plus cher et manque une section ; `data-only` passe mais ne teste pas l'accès MCP.
- Sur le portefeuille, les deux terminent ; la skill va plus vite et tient mieux la règle « corrélation ≠ causalité ».
- `data-only` montre qu'un pack gelé suffit parfois au contrat : le bénéfice propre du MCP n'est donc pas isolé. La skill améliore la **discipline de processus**, pas seulement la capacité.
- Une exécution ne prouve pas une supériorité générale. Il faut au moins 3 répétitions (idéalement 5), une grille humaine et des cas supplémentaires avant de conclure.

## Ce qu'il faudrait pour une preuve

Les trois bras agent sont exécutables ; le bras humain reste à importer via `--human-dir` (aucune revue humaine n'a été fabriquée). Il faut cinq répétitions, clés de correction écrites avant les runs, notation aveugle, intervalles de confiance et décision de gouvernance go/no-go.

## Commandes de reproduction

Voir `README.md` du plugin, puis :

```bash
claude -p "<prompt>" \
  --mcp-config /tmp/meridian-mcp.json \
  --strict-mcp-config \
  --allowedTools "Skill,Read,mcp__meridian__meridian_analyser,mcp__meridian__meridian_portefeuille" \
  --max-budget-usd 1.25 \
  --output-format stream-json --verbose --include-partial-messages
```
