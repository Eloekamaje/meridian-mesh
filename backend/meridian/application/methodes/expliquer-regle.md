---
nom: expliquer-regle
description: On demande comment l'application décide, contrôle, autorise, calcule ou applique une règle.
---
# Expliquer une règle de l'application

1. Trouvez la règle dans le code : chercher_texte ou chercher_symbole, puis lire_code sur les lignes qui
   l'appliquent. Ne décrivez jamais une règle que vous n'avez pas lue.
2. Énoncez-la en une phrase métier : « Quand <situation>, l'application <effet> », avec sa citation.
3. Donnez un exemple concret, avec des valeurs plausibles tirées du code.
4. Signalez les exceptions et les cas limites visibles dans le code (conditions, valeurs par défaut).
5. Dites si la règle est confirmée par l'équipe. Sinon, et si elle est utile et prouvée, proposez-la avec
   proposer_connaissance (type BUSINESS_RULE) et dites que l'équipe pourra la confirmer.
6. Deux questions de suite.
