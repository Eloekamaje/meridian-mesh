---
nom: evaluer-impact
description: On demande ce qui se passe si l'application change, tombe ou si une de ses dépendances change.
---
# Évaluer l'impact d'un changement ou d'une panne

0. Dans un Travail, commencez par planifier (planifier) : une étape par point ci-dessous, avant tout autre outil.
1. Reformulez le changement envisagé en une phrase.
2. Écrivez les hypothèses dont dépend la réponse, une par une (proposer_hypothese) : par exemple « aucune autre
   application n'appelle X », « X garde ses données sur une seule base », « X ne dépend d'aucun tiers ».
3. Mettez chaque hypothèse à l'épreuve AVANT de conclure : tracer_appels (inbound, outbound), lire_code,
   mes_connaissances, et consulter_jumeau pour les autres applications autorisées, dans le même tour si possible
   (elles sont consultées en parallèle). Inscrivez le résultat avec eprouver_hypothese : « tient » ou « tombe »
   avec les citations lues, sinon « indecise ».
4. Ce qui dépend de l'élément touché, regroupé par usage métier plutôt que par fonction technique ; puis ce dont il
   dépend : dépendances, stockage, déploiement.
5. La note d'impact : une ligne par effet, classée **bloquant**, **dégradé**, **sans effet visible** ou **inconnu**,
   et sa citation sur la même ligne. Un effet sans citation est classé **inconnu** et dit quelle source le
   trancherait (exploitation, équipe, autre jumeau).
6. Ce que le code ne permet pas de savoir (trafic réel, utilisateurs touchés, appelants hors du code).
7. Une recommandation prudente, présentée comme une piste à valider par l'équipe.
8. Déposez la note (deposer_livrable « Note d'impact — … ») et levez chaque étape faite avec lever_etape.
