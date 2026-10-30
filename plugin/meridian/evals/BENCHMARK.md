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

| Condition | Résultat | Tours | Durée | Coût | Outils |
|---|---|---:|---:|---:|---|
| Avec `incident-ops` | **Passe** : socle, preuves, SLA, limites, autorité, prochaines étapes | 9 | 77 s | 0,56 USD | 2 appels `meridian_analyser` |
| Sans skill | **Échoue** : réponse produite, mais sections `actions` et `prochaines_etapes` absentes | 22 | 144 s | 1,23 USD | 10+ appels Claims/impact/portefeuille |

## Workflow 2 — portefeuille Paiement

Prompt : concentration de valeur et de risque dans le domaine Paiement, avec Value Ledger.

| Condition | Résultat | Tours | Durée | Coût | Outils |
|---|---|---:|---:|---:|---|
| Avec `enterprise-portfolio` | Réponse complète, Value Ledger, limites, aucune causalité affirmée | 10 | 70 s | 0,58 USD | 2 outils (portefeuille + valeur) |
| Sans skill | Réponse complète mais plus longue, commence par « chaîne causale » puis la corrige | 16 | 143 s | 0,64 USD | 5 outils |

## Lecture

Ce dispositif ne permet pas d'affirmer que Méridian améliore les décisions : les deux bras ont Méridian, n=1. Il permet de dire que la skill passe les critères de structure et réduit le coût/temps sur ce cas, pas qu'elle produit une meilleure décision business.

- Sur l'incident, le baseline finit par répondre mais coûte 2,2× plus cher, prend 1,9× plus de temps et manque
  les sections de décision attendues ; la skill termine dans le budget et passe les critères objectifs.
- Sur le portefeuille, les deux terminent ; la skill va plus vite et tient mieux la règle « corrélation ≠ causalité ».
- Le baseline reste capable de répondre : la skill améliore la **discipline de processus**, pas la seule capacité.
- Une exécution ne prouve pas une supériorité générale. Il faut 3 répétitions, une grille humaine et des cas
  supplémentaires avant de conclure.

## Ce qu'il faudrait pour une preuve

Quatre bras : skill+MCP, checklist générique+MCP, données gelées sans MCP, analyste humain. Cinq répétitions, clés de correction écrites avant les runs, notation aveugle, intervalles de confiance, et décision de gouvernance go/no-go. Voir la revue ECC du 2026-10-30.

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
