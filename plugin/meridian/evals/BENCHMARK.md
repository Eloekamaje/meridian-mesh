# Benchmark skills Méridian — 2026-10-30

## But

Comparer une exécution **avec skill** et **sans skill** sur deux workflows bancaires, avec le même MCP
Méridian read-only et le même modèle. Ce benchmark est un signal, pas une preuve statistique.

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

| Condition | Résultat | Tours | Coût | Outils |
|---|---|---:|---:|---|
| Avec `incident-ops` | Réponse complète avec socle, preuves, SLA, limites, autorité | 13 | 0,60 USD | 2 appels `meridian_analyser` |
| Sans skill | **Timeout 150 s**, pas de réponse finale | 21+ | >0,75 USD | 10 appels Claims + impact + portefeuille + valeurs |

## Workflow 2 — portefeuille Paiement

Prompt : concentration de valeur et de risque dans le domaine Paiement, avec Value Ledger.

| Condition | Résultat | Tours | Coût | Outils |
|---|---|---:|---:|---|
| Avec `enterprise-portfolio` | Réponse complète, Value Ledger, limites, aucune causalité affirmée | 10 | 0,58 USD | 2 outils (portefeuille + valeur) |
| Sans skill | Réponse complète mais plus longue, commence par « chaîne causale » puis la corrige | 16 | 0,64 USD | 5 outils |

## Lecture

- Sur l'incident, la skill évite l'errance et produit la structure attendue ; le baseline sans skill part dans
  l'exploration et ne termine pas dans le budget.
- Sur le portefeuille, les deux terminent ; la skill va plus vite et tient mieux la règle « corrélation ≠ causalité ».
- Le baseline reste capable de répondre : la skill améliore la **discipline de processus**, pas la seule capacité.
- Une exécution ne prouve pas une supériorité générale. Il faut 3 répétitions, une grille humaine et des cas
  supplémentaires avant de conclure.

## Commandes de reproduction

Voir `README.md` du plugin, puis :

```bash
claude -p "<prompt>" \
  --mcp-config /tmp/meridian-mcp.json \
  --strict-mcp-config \
  --allowedTools "Skill,Read,mcp__meridian__meridian_analyser,mcp__meridian__meridian_portefeuille" \
  --max-budget-usd 0.75 \
  --output-format stream-json --verbose --include-partial-messages
```
