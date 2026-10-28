# MÉRIDIAN — Relevé de latence du 2026-10-28
## Premier mot et réponse complète, mesurés par le banc, pas estimés

**Statut :** Relevé, à joindre à toute affirmation de performance
**Version :** 1.0
**Date :** 2026-10-28
**Document lié :** `MERIDIAN_Plan_Remediation_v1.md` (L2.4), Écarts §2 capacité 10

---

# 0. Pourquoi ce document existe

Le document d'écarts affirmait « le premier texte arrive en 2 s » et « réponse relue en 12 à 22 s » sans qu'aucun
instrument ne produise ces chiffres : le banc ne chronométrait que la fin de la réponse complète. Le premier mot est
désormais mesuré par Flore elle-même (`durees.premier_texte`, `Chrono.texte`), dans **tous** les chemins, et ce
relevé est la première publication qui s'appuie dessus.

# 1. Conditions

| Élément | Valeur |
|---|---|
| Commande | `python -m jumeau.latence --repetitions 1` |
| Modèle | `deepseek-chat`, API hébergée (`api.deepseek.com`) |
| Repères | les quatre questions de `jumeau/latence.py` |
| Objectifs du banc | 2,0 s (simple) · 5,0 s (analyse) |
| Chemin | celui de l'écran : Flore diffuse au fil de l'eau (`emit`) |
| Répétitions | **1** — voir §4 |

# 2. Résultats

| Classe | Question | Réponse complète | **Premier mot** | Objectif |
|---|---|---|---|---|
| simple | qui es-tu ? | 6,0 s | **1,5 s** | 2,0 s |
| simple | que fait Conduit ? | 11,2 s | **3,3 s** | 2,0 s |
| analyse | comment fonctionne la publication d'un article sur Conduit ? · schéma dessiné | 17,4 s | **10,2 s** | 5,0 s |
| analyse | illustre-moi avec un schéma la publication d'un article dans Conduit · schéma dessiné | 21,0 s | **0,8 s** | 5,0 s |

Détail des phases (médiane de la passe unique) :

| Question | contexte | modèle | outils | relecture | contrôles |
|---|---|---|---|---|---|
| qui es-tu ? | 0,1 | 4,0 | 0 | 1,6 | 0,0 |
| que fait Conduit ? | 0,0 | 8,9 | 0,0 | 2,2 | 0,0 |
| comment fonctionne la publication… | 0,0 | 13,8 | 1,6 | 1,9 | 0,0 |
| illustre-moi avec un schéma… | 0,0 | 18,7 | 0,4 | 1,9 | 0,0 |

# 3. Ce que ces chiffres disent

- **Une seule question sur quatre tient l'objectif** sur le premier mot (1,5 s < 2,0 s). Une seconde l'approche
  (0,8 s) mais son premier mot est un préambule : la réponse utile arrive bien plus tard.
- **Aucune réponse complète n'atteint l'objectif des exigences non fonctionnelles** (< 5 s pour une analyse) : la
  plus rapide est à 6,0 s, la plus lente à 21,0 s.
- **La relecture coûte 1,6 à 2,2 s** sur chaque réponse, et elle n'est pas compressible sans supprimer le contrôle.
- **Le modèle est le poste dominant** (4,0 à 18,7 s sur 6,0 à 21,0 s), les outils de code très secondaires (0 à 1,6 s)
  sur ces quatre questions.

# 4. Ce que ces chiffres ne disent pas

**Une seule répétition par question.** Il n'y a donc ni p50 ni p95 : le banc affiche la même valeur aux deux, et ce
n'est pas une dispersion nulle, c'est une dispersion inconnue. Deux passes faites le même jour, à quelques minutes
d'intervalle, donnent **9,1 s puis 11,2 s** pour la même question — un écart de 23 % qui interdit de publier une
tendance à partir d'un point.

Pour publier une tendance : `--repetitions 5` au moins, et une comparaison entre deux versions du code ou du modèle.
Le coût est réel (chaque passe appelle le modèle une fois par question, plus une relecture), d'où la répétition
unique de ce premier relevé.

# 5. Comment refaire ce relevé

```bash
cd backend && set -a && . ./.env && set +a
.venv/bin/python -m jumeau.latence --repetitions 5
```

Le banc imprime, par question : p50 et p95 de la réponse complète, **p50 du premier mot**, et le détail des phases.
Tout chiffre de performance cité dans un document doit venir de cette sortie, avec sa date et son nombre de passes.
