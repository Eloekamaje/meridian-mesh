---
nom: suivre-les-changements
description: On demande ce qui a changé dans l'application, depuis quand, pourquoi, ou ce qu'un changement récent peut casser.
---
# Suivre les changements de l'application

0. Dans un Travail, commencez par planifier (planifier) : période, changements, risques, synthèse.
1. Fixez la période : la date donnée par l'interlocuteur, sinon les trente derniers jours (calculez la date).
2. ce_qui_a_change(depuis) : commits, connaissances apparues et disparues.
3. Regroupez les changements par effet métier (nouveau service, service retiré, nouvelle dépendance, règle
   modifiée) plutôt que commit par commit. Le message de chaque changement dit souvent pourquoi il a été fait.
4. Pour chaque changement qui compte, une citation `chemin#Ldébut-Lfin` lue avec lire_code ; pour un service
   retiré, cherchez qui l'appelait (tracer_appels, chercher_texte) : c'est là que se trouve le risque.
5. Distinguez ce qui est sans effet visible, ce qui change un comportement, ce qui peut casser.
6. Dans un Travail : déposez les risques comme hypothèses à vérifier, et une synthèse comme livrable si on
   vous la demande.
7. Ce que l'historique ne dit pas (déploiement réel, date de mise en production, utilisateurs touchés) et qui
   peut le dire (exploitation, équipe).
7. Levez chaque étape faite avec lever_etape, une ligne chacune.
