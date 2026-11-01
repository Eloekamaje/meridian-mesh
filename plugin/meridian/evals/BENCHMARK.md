# Smoke test skills Méridian — 2026-10-30

> **Note 2026-11-01** : les runs réels du pilote utilisent désormais
> [`run_deepseek.py`](run_deepseek.py) sur le backend `JUMEAU_MODELE=deepseek`, **sans Claude
> Code**. Les chiffres ci-dessous proviennent du harness Claude Code historique et ne doivent pas
> être relus comme un résultat DeepSeek. Voir [`PILOT-2026-11-01.md`](PILOT-2026-11-01.md).

## But

Comparer une exécution **avec skill** et **sans skill** sur deux workflows bancaires, avec le même MCP
Méridian read-only et le même modèle. Ce benchmark est un **smoke test**, pas une preuve statistique ni une preuve de valeur business. Il ne mesure pas l'effet Méridian sans MCP, ni la qualité décisionnelle contre un analyste humain.

## Protocole

- Harness : Claude Code 2.1.314, `claude -p`, MCP Méridian local.
- Modèle : `deepseek-flash` (session).
- Budget : 0,75 USD par run, timeout 300 s.
- Avec skill : projet contenant `.claude/skills/meridian-*`.
- Sans skill : répertoire vide, même MCP, même prompt.
- Une exécution par condition ; aucune moyenne, aucun test statistique.

## Workflow 1 — incident Paiements

Prompt : incident depuis 14 h, SLA menacé, contexte `sit-latence-paiements`, Twins `paiements`/`comptes`,
application `conduit`.

| Bras | Résultat | Durée moyenne | Coût moyen | Outils |
|---|---|---:|---:|---|
| `skill+mcp` | **5/5** | 113 s | 0,77 USD | Skill + MCP |
| `checklist+mcp` | **0/5** | 173 s | 1,31 USD | checklist + MCP |
| `data-only` | **0/5** | 84 s | 0,55 USD | pack gelé, aucun outil |
| `human` | non exécuté | — | — | packet de 12 échantillons prêt |

## Workflow 2 — changement réglementaire

Prompt : impact de la règle R-118 sur `conduit`, avec impact prouvé/inféré/inconnu et approbation.

| Bras | Résultat | Durée | Coût |
|---|---|---:|---:|
| `skill+mcp` | **5/5** | 143 s | 0,95 USD |
| `checklist+mcp` | 1/5 | 135 s | 1,02 USD |
| `data-only` | 1/5 | 78 s | 0,52 USD |
| `human` | non exécuté | — | — |

Le bras skill a dû être porté à **2,00 USD** de budget : trois runs à 1,25 USD étaient épuisés avant
la réponse finale. La comparaison de coût doit donc être lue avec ce budget différent.

**Portefeuille (smoke antérieur, hors runner)** : avec `enterprise-portfolio` 10 tours / 0,58 USD ;
sans skill 16 tours / 0,64 USD, avec une ouverture « chaîne causale » ensuite corrigée.

## Lecture

Ce dispositif ne permet pas d'affirmer que Méridian améliore les décisions : n=5, données demo, pas de revue humaine. `skill+mcp` passe 5/5 mais le format est explicitement imposé par la skill ; `data-only` et `checklist+mcp` échouent surtout sur les sections attendues. Ce n'est pas une preuve de qualité décisionnelle.

- Sur l'incident, `skill+mcp` passe 5/5 ; `checklist+mcp` et `data-only` échouent sur le contrat de sections, et la checklist coûte plus cher. Le format imposé par la skill crée un avantage mesuré qui n'est pas encore une preuve de meilleure décision.
- Sur le portefeuille, les deux terminent ; la skill va plus vite et tient mieux la règle « corrélation ≠ causalité ».
- `data-only` échoue aussi sur le contrat : un pack gelé ne suffit pas ici. Le bénéfice propre du MCP n'est pas isolé ; la skill améliore surtout la **discipline de processus**.
- Les deux scénarios ont maintenant 5 répétitions skill, mais R-118 exige un budget supérieur ; le panel de revue est un panel d'agents, pas d'humains.

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
