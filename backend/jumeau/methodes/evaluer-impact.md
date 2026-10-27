---
nom: evaluer-impact
description: On demande ce qui se passe si l'application change, tombe ou si une de ses dépendances change.
---
# Évaluer l'impact d'un changement ou d'une panne

1. Reformulez le changement envisagé en une phrase.
2. Ce qui dépend de l'élément touché : tracer_appels (sens inbound) et mes_connaissances. Regroupez par
   usage métier plutôt que par fonction technique.
3. Ce dont il dépend : tracer_appels (sens outbound), dépendances et stockage.
4. Classez les effets : bloquant, dégradé, sans effet visible. Chaque effet a sa citation.
5. Ce que le code ne permet pas de savoir (trafic réel, utilisateurs touchés, autres applications
   appelantes) et la source qui le dirait (exploitation, équipe, autres jumeaux).
6. Une recommandation prudente, présentée comme une piste à valider par l'équipe.
